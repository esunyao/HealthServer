package cn.esuny.healthmind.infrastructure.database

import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.TaskExecutionException
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.transaction.annotation.Transactional

@Component
class RecoveryAndRetentionJobs(
    private val jdbc: JdbcTemplate,
    private val tasks: TaskCommandRepository,
) {
    @Scheduled(fixedDelayString = "\${healthmind.scheduler.recovery-fixed-delay:PT1M}")
    @Transactional
    fun recoverStaleWork() {
        jdbc.update(
            """
            UPDATE healthmind.integration_outbox
               SET status='failed', failure_code='PUBLISHER_INTERRUPTED', failure_message='Recovered stale publisher', next_attempt_at=NOW()
             WHERE status='publishing' AND next_attempt_at < NOW()
            """.trimIndent(),
        )
        jdbc.update(
            """
            UPDATE healthmind.ai_task_attempts a
               SET status='timed_out', finished_at=NOW(), failure_category='timeout', failure_code='ATTEMPT_TIMEOUT',
                   failure_message='Execution exceeded configured timeout'
              FROM healthmind.ai_tasks t
             WHERE a.task_id=t.task_id AND a.status='running' AND a.started_at + (a.timeout_ms * INTERVAL '1 millisecond') < NOW()
            """.trimIndent(),
        )
        tasks.claimTimedOut().forEach { execution ->
            tasks.fail(
                execution,
                TaskExecutionException(
                    "ATTEMPT_TIMEOUT",
                    FailureCategory.TIMEOUT,
                    "Execution exceeded configured timeout",
                ),
                FailureCategory.TIMEOUT,
                "ATTEMPT_TIMEOUT",
            )
        }
    }

    @Scheduled(cron = "0 20 3 * * *")
    @Transactional
    fun purgeExpiredRows() {
        jdbc.update("DELETE FROM healthmind.ai_task_results WHERE expires_at < NOW()")
        jdbc.update("DELETE FROM healthmind.integration_inbox WHERE retention_until < NOW() AND status IN ('processed','failed')")
        jdbc.update("DELETE FROM healthmind.integration_outbox WHERE retention_until < NOW() AND status='published'")
        jdbc.update("DELETE FROM healthmind.ai_tasks WHERE retention_until < NOW() AND status IN ('succeeded','failed','cancelled','expired')")
    }
}
