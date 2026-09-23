package cn.esuny.healthmind.application.service

import cn.esuny.healthmind.application.port.out.AgentRunPort
import cn.esuny.healthmind.application.port.out.AgentRunState
import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.AgentSubmissionState
import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.domain.task.TaskExecutionException
import cn.esuny.healthmind.infrastructure.database.TaskCommandRepository
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import cn.esuny.healthmind.infrastructure.json.JsonSchemaService
import io.micrometer.core.instrument.MeterRegistry
import org.slf4j.LoggerFactory
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Service

@Service
class TaskExecutionService(
    private val repository: TaskCommandRepository,
    private val agent: AgentRunPort,
    private val schemaService: JsonSchemaService,
    private val canonicalJson: CanonicalJson,
    private val meters: MeterRegistry,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    @Scheduled(fixedDelayString = "\${healthmind.scheduler.task-fixed-delay:PT1S}")
    fun claimNext() {
        repository.claimNext()
    }

    @Scheduled(fixedDelayString = "\${healthmind.scheduler.task-fixed-delay:PT1S}")
    fun advanceNext() {
        val command = repository.claimDue() ?: return
        if (command.agentRunId == null) {
            try {
                val runId = if (command.agentSubmissionState == AgentSubmissionState.NEW) {
                    agent.start(command)
                } else {
                    agent.reconcile(command)
                }
                if (runId == null) repository.schedulePoll(command) else repository.attachRun(command, runId)
            } catch (exception: TaskExecutionException) {
                if (exception.category.retryable && command.agentSubmissionState == AgentSubmissionState.NEW) {
                    if (exception.safeToRetrySubmission) repository.resetSubmission(command)
                    else repository.markSubmissionUnknown(command)
                } else {
                    handleAgentError(command, exception)
                }
            }
            return
        }
        val state = try {
            agent.inspect(command)
        } catch (exception: TaskExecutionException) {
            handleAgentError(command, exception)
            return
        }
        when (state) {
            AgentRunState.Active -> repository.schedulePoll(command)
            is AgentRunState.Failed -> fail(command, TaskExecutionException(state.code, state.category, state.summary))
            is AgentRunState.Succeeded -> {
                val output = try {
                    val node = canonicalJson.parse(state.result.outputJson)
                    if (node.path("status").asString() == "needs_review") {
                        val reason = node.path("reason_code").asString().take(64)
                        throw TaskExecutionException("AGENT_NEEDS_REVIEW", FailureCategory.PERMANENT, "Agent requested review: $reason")
                    }
                    schemaService.validate(command.outputSchema, node)
                    node
                } catch (exception: TaskExecutionException) {
                    fail(command, exception)
                    return
                } catch (exception: Exception) {
                    fail(command, TaskExecutionException("AGENT_OUTPUT_INVALID", FailureCategory.CONTRACT, "Agent output is not valid JSON", exception))
                    return
                }
                repository.complete(command, state.result, output)
                meters.counter("healthmind.tasks", "outcome", "succeeded").increment()
            }
        }
    }

    private fun handleAgentError(command: TaskExecution, exception: TaskExecutionException) {
        if (exception.category.retryable) {
            log.warn("Agent request unavailable for task {} attempt {}: {}", command.taskId, command.attemptId, exception.code)
            repository.schedulePoll(command)
        } else {
            fail(command, exception)
        }
    }

    private fun fail(command: TaskExecution, exception: TaskExecutionException) {
        repository.fail(command, exception, exception.category, exception.code)
        meters.counter("healthmind.tasks", "outcome", "failed", "category", exception.category.wireValue).increment()
        log.warn("HealthMind task {} attempt {} failed with code {}", command.taskId, command.attemptNo, exception.code)
    }
}
