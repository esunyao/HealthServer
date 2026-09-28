package cn.esuny.healthmind.infrastructure.database

import cn.esuny.healthmind.application.port.out.AgentRunPort
import cn.esuny.healthmind.application.port.out.TaskOutcomePort
import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.TaskExecutionException
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
    private val taskOutcomes: TaskOutcomePort,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    @Scheduled(fixedDelayString = "\${healthmind.scheduler.recovery-fixed-delay:PT1M}")
    fun recoverStaleWork() {
        jdbc.update(
            """
            UPDATE healthmind.integration_outbox
               SET status='failed', failure_code='PUBLISHER_INTERRUPTED', failure_message='Recovered stale publisher',
                   next_attempt_at=NOW(), claim_version=claim_version+1
             WHERE status='publishing' AND next_attempt_at < NOW()
            """.trimIndent(),
        )
        tasks.claimTimedOut().forEach { execution ->
            val unknownSubmission = execution.agentRunId == null && execution.agentSubmissionState != cn.esuny.healthmind.domain.task.AgentSubmissionState.NEW
            val code = if (unknownSubmission) "AGENT_SUBMISSION_INDETERMINATE" else "ATTEMPT_TIMEOUT"
            val category = if (unknownSubmission) FailureCategory.PERMANENT else FailureCategory.TIMEOUT
            val failure = TaskExecutionException(
                code,
                category,
                if (unknownSubmission) "Agent run submission could not be confirmed" else "Execution exceeded configured timeout",
            )
            tasks.fail(
                execution,
                failure,
                category,
                code,
                taskOutcomes.failedEvent(execution, category, code, failure.message ?: code),
            )
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
        jdbc.update("DELETE FROM healthmind.ai_tool_invocations WHERE task_id IN (SELECT task_id FROM healthmind.ai_tasks WHERE retention_until < NOW() AND status IN ('succeeded','failed','cancelled','expired'))")
        jdbc.update("DELETE FROM healthmind.ai_task_artifacts WHERE expires_at < NOW() AND status='deleted'")
        jdbc.update(
            """DELETE FROM healthmind.ai_task_attempts a
                USING healthmind.ai_tasks t
                WHERE t.task_id=a.task_id
                  AND t.retention_until < NOW() AND t.status IN ('succeeded','failed','cancelled','expired')
                  AND a.status NOT IN ('pending','running')
                  AND NOT EXISTS (SELECT 1 FROM healthmind.ai_task_results r WHERE r.attempt_id=a.attempt_id)
                  AND NOT EXISTS (SELECT 1 FROM healthmind.ai_tool_invocations i WHERE i.attempt_id=a.attempt_id)
                  AND NOT EXISTS (SELECT 1 FROM healthmind.ai_task_artifacts artifact WHERE artifact.attempt_id=a.attempt_id)""",
        )
        jdbc.update(
            """DELETE FROM healthmind.ai_tasks t
                WHERE t.retention_until < NOW() AND t.status IN ('succeeded','failed','cancelled','expired')
                  AND NOT EXISTS (SELECT 1 FROM healthmind.ai_task_attempts a WHERE a.task_id=t.task_id)
                  AND NOT EXISTS (SELECT 1 FROM healthmind.ai_task_results r WHERE r.task_id=t.task_id)
                  AND NOT EXISTS (SELECT 1 FROM healthmind.ai_tool_invocations i WHERE i.task_id=t.task_id)
                  AND NOT EXISTS (SELECT 1 FROM healthmind.integration_outbox o WHERE o.task_id=t.task_id)
                  AND NOT EXISTS (SELECT 1 FROM healthmind.ai_task_artifacts a WHERE a.task_id=t.task_id)""",
        )
    }
}
