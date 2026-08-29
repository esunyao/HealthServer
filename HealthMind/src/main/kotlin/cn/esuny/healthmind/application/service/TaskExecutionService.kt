package cn.esuny.healthmind.application.service

import cn.esuny.healthmind.application.port.out.DifyWorkflowPort
import cn.esuny.healthmind.domain.task.FailureCategory
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
    private val dify: DifyWorkflowPort,
    private val schemaService: JsonSchemaService,
    private val canonicalJson: CanonicalJson,
    private val meters: MeterRegistry,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    @Scheduled(fixedDelayString = "\${healthmind.scheduler.task-fixed-delay:PT1S}")
    fun executeNext() {
        val command = repository.claimNext() ?: return
        try {
            val result = dify.run(command)
            val resultNode = canonicalJson.parse(result.outputJson)
            schemaService.validate(command.outputSchema, resultNode)
            repository.complete(command, result, resultNode)
            meters.counter("healthmind.tasks", "outcome", "succeeded").increment()
        } catch (exception: TaskExecutionException) {
            repository.fail(command, exception, exception.category, exception.code)
            meters.counter("healthmind.tasks", "outcome", "failed", "category", exception.category.wireValue).increment()
            log.warn("HealthMind task {} attempt {} failed with code {}", command.taskId, command.attemptNo, exception.code)
        } catch (exception: Exception) {
            repository.fail(command, exception, FailureCategory.TRANSIENT, "UNEXPECTED_EXECUTION_ERROR")
            meters.counter("healthmind.tasks", "outcome", "failed", "category", "transient").increment()
            log.warn("HealthMind task {} attempt {} failed unexpectedly", command.taskId, command.attemptNo)
        }
    }
}
