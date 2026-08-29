package cn.esuny.healthmind.interfaces.messaging

import cn.esuny.contracts.integration.v1.IntegrationEvent
import cn.esuny.contracts.integration.v1.NutritionCaptureReadyPayload
import cn.esuny.contracts.integration.v1.NutritionEventTypes
import cn.esuny.healthmind.infrastructure.database.TaskCommandRepository
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import org.springframework.kafka.annotation.KafkaListener
import org.springframework.stereotype.Component
import java.time.Instant
import java.util.UUID

@Component
class NutritionCaptureReadyListener(
    private val canonicalJson: CanonicalJson,
    private val repository: TaskCommandRepository,
) {
    @KafkaListener(
        topics = ["\${healthmind.kafka.capture-ready-destination}"],
        groupId = "\${healthmind.kafka.consumer-group}",
    )
    fun receive(raw: String) {
        val root = canonicalJson.parse(raw)
        require(root.path("event_type").asString() == NutritionEventTypes.CAPTURE_READY) { "Unsupported event_type" }
        require(root.path("schema_version").asString() == NutritionEventTypes.SCHEMA_VERSION) { "Unsupported schema_version" }
        val payload = root.path("payload")
        val event = IntegrationEvent(
            eventId = UUID.fromString(root.path("event_id").asString()),
            eventType = root.path("event_type").asString(),
            occurredAt = Instant.parse(root.path("occurred_at").asString()),
            producer = root.path("producer").asString(),
            traceId = root.path("trace_id").asString(),
            subjectId = UUID.fromString(root.path("subject_id").asString()),
            aggregateType = root.path("aggregate_type").asString(),
            aggregateId = root.path("aggregate_id").asString(),
            schemaVersion = root.path("schema_version").asString(),
            payload = NutritionCaptureReadyPayload(
                captureSessionId = payload.path("capture_session_id").asLong(),
                mealId = payload.path("meal_id").asLong(),
            ),
        )
        repository.acceptCaptureReady(event, canonicalJson.sha256(root))
    }
}
