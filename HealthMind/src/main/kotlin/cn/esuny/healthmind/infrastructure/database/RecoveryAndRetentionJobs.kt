package cn.esuny.healthmind.infrastructure.database

import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.transaction.annotation.Transactional

@Component
class RecoveryAndRetentionJobs(private val jdbc: JdbcTemplate) {
    @Scheduled(fixedDelayString = "\${healthmind.scheduler.recovery-fixed-delay:PT1M}")
    @Transactional
    fun recoverStaleWork() {
        jdbc.update(
            """
            UPDATE healthmind.integration_outbox
               SET status='failed', failure_code='PUBLISHER_INTERRUPTED', failure_message='Recovered stale publisher', next_attempt_at=NOW()
             WHERE status='publishing' AND created_at < NOW() - INTERVAL '5 minutes'
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
        jdbc.update(
            """
            UPDATE healthmind.ai_tasks t
               SET status='queued', next_attempt_at=NOW(), lock_version=lock_version+1
             WHERE t.status='running' AND EXISTS (
                 SELECT 1 FROM healthmind.ai_task_attempts a
                  WHERE a.task_id=t.task_id AND a.status='timed_out' AND a.finished_at > NOW() - INTERVAL '2 minutes'
             )
            """.trimIndent(),
        )
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
