package cn.esuny.healthmind.infrastructure.database

import cn.esuny.healthmind.application.port.out.AgentRunPort
import org.slf4j.LoggerFactory
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.transaction.annotation.Transactional

@Component
class RecoveryAndRetentionJobs(
    private val jdbc: JdbcTemplate,
    private val tasks: TaskCommandRepository,
    private val agent: AgentRunPort,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    @Scheduled(fixedDelayString = "\${healthmind.scheduler.recovery-fixed-delay:PT1M}")
    fun recoverStaleWork() {
        jdbc.update(
            """
            UPDATE healthmind.integration_outbox
               SET status='failed', failure_code='PUBLISHER_INTERRUPTED', failure_message='Recovered stale publisher', next_attempt_at=NOW()
             WHERE status='publishing' AND next_attempt_at < NOW()
            """.trimIndent(),
        )
        tasks.recoverTimedOut().forEach { execution ->
            try {
                agent.cancel(execution)
            } catch (exception: Exception) {
                log.warn("Could not cancel expired agent run for attempt {}", execution.attemptId)
            }
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
