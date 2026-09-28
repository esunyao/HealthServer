package cn.esuny.healthmind.application.service

import cn.esuny.contracts.integration.v1.NutritionCaptureReadyPayload
import cn.esuny.contracts.integration.v1.NutritionEventTypes
import cn.esuny.healthmind.application.port.out.TaskOutcomePort
import cn.esuny.healthmind.application.port.out.TaskOutboxMessage
import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import org.springframework.stereotype.Component
import tools.jackson.databind.JsonNode
import tools.jackson.databind.ObjectMapper
import tools.jackson.databind.node.ObjectNode
import java.util.UUID

@Component
class MealTaskAdapter(
    private val objectMapper: ObjectMapper,
    private val canonicalJson: CanonicalJson,
    private val properties: HealthMindProperties,
) : TaskOutcomePort {
    fun submission(payload: NutritionCaptureReadyPayload): TaskSubmission {
        val manifest = objectMapper.createObjectNode()
            .put("capture_session_id", payload.captureSessionId.toString())
            .put("meal_id", payload.mealId)
        return TaskSubmission(MEAL_ANALYSIS_TASK_TYPE, canonicalJson.stringify(manifest))
    }

    fun context(contextManifest: String): MealContext {
        val manifest = canonicalJson.parse(contextManifest)
        val captureSessionId = runCatching {
            UUID.fromString(manifest.path("capture_session_id").asString())
        }.getOrElse { throw IllegalArgumentException("Meal task context has an invalid capture_session_id", it) }
        val mealId = manifest.path("meal_id").asLong()
        require(mealId > 0) { "Meal task context has an invalid meal_id" }
        return MealContext(captureSessionId, mealId)
    }

    override fun completedEvent(command: TaskExecution, result: JsonNode): TaskOutboxMessage {
        require(command.taskTypeCode == MEAL_ANALYSIS_TASK_TYPE) { "Meal adapter cannot handle ${command.taskTypeCode}" }
        val meal = context(command.contextManifest)
        val eventId = UUID.randomUUID()
        val payload = (result.deepCopy() as? ObjectNode)
            ?: throw IllegalArgumentException("Meal analysis result must be an object")
        payload.put("task_id", command.taskId.toString())
            .put("capture_session_id", meal.captureSessionId.toString())
            .put("meal_id", meal.mealId)
            .put("result_version", 1)
        return TaskOutboxMessage(
            eventId = eventId,
            eventType = NutritionEventTypes.ANALYSIS_COMPLETED,
            schemaVersion = NutritionEventTypes.SCHEMA_VERSION,
            destinationKey = properties.kafka.analysisCompletedDestination,
            partitionKey = meal.captureSessionId.toString(),
            payload = integrationEnvelope(command, eventId, NutritionEventTypes.ANALYSIS_COMPLETED, payload),
        )
    }

    override fun failedEvent(
        command: TaskExecution,
        category: FailureCategory,
        code: String,
        message: String,
    ): TaskOutboxMessage {
        require(command.taskTypeCode == MEAL_ANALYSIS_TASK_TYPE) { "Meal adapter cannot handle ${command.taskTypeCode}" }
        val meal = context(command.contextManifest)
        val eventId = UUID.randomUUID()
        val payload = objectMapper.createObjectNode()
            .put("task_id", command.taskId.toString())
            .put("capture_session_id", meal.captureSessionId.toString())
            .put("meal_id", meal.mealId)
            .put("error_code", code)
            .put("failure_category", category.wireValue)
            .put("retryable", category.retryable)
            .put("error_summary", message.take(500))
        return TaskOutboxMessage(
            eventId = eventId,
            eventType = NutritionEventTypes.ANALYSIS_FAILED,
            schemaVersion = NutritionEventTypes.SCHEMA_VERSION,
            destinationKey = properties.kafka.analysisFailedDestination,
            partitionKey = meal.captureSessionId.toString(),
            payload = integrationEnvelope(command, eventId, NutritionEventTypes.ANALYSIS_FAILED, payload),
        )
    }

    private fun integrationEnvelope(
        command: TaskExecution,
        eventId: UUID,
        eventType: String,
        payload: JsonNode,
    ): JsonNode {
        val envelope = objectMapper.createObjectNode()
            .put("event_id", eventId.toString())
            .put("event_type", eventType)
            .put("occurred_at", java.time.Instant.now().toString())
            .put("producer", "HealthMind")
            .put("trace_id", command.traceId)
            .put("subject_id", command.subjectId?.toString())
            .put("aggregate_type", command.aggregateType)
            .put("aggregate_id", command.aggregateId)
            .put("schema_version", NutritionEventTypes.SCHEMA_VERSION)
        envelope.set("payload", payload)
        return envelope
    }

    data class MealContext(val captureSessionId: UUID, val mealId: Long)

    data class TaskSubmission(val taskTypeCode: String, val contextManifest: String)

    companion object {
        const val MEAL_ANALYSIS_TASK_TYPE = "nutrition.meal_analysis"
    }
}
