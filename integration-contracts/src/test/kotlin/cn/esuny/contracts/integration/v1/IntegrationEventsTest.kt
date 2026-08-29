package cn.esuny.contracts.integration.v1

import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule
import com.fasterxml.jackson.module.kotlin.registerKotlinModule
import java.time.Instant
import java.util.UUID
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class IntegrationEventsTest {
    private val mapper = ObjectMapper().registerKotlinModule().registerModule(JavaTimeModule())

    @Test
    fun `serializes public fields as snake case`() {
        val event = IntegrationEvent(
            eventId = UUID.fromString("b8da3ce9-a537-40fd-a94b-9146162158ac"),
            eventType = NutritionEventTypes.CAPTURE_READY,
            occurredAt = Instant.parse("2026-08-29T00:00:00Z"),
            producer = "NutriMemo",
            traceId = "trace-1",
            subjectId = UUID.fromString("ce9cb0fe-0c58-4a66-9f7e-a25c788520dc"),
            aggregateType = "meal",
            aggregateId = "12",
            payload = NutritionCaptureReadyPayload(UUID.fromString("6078e44f-4d34-424a-af6d-fe2ad886ae84"), 12),
        )

        val json = mapper.writeValueAsString(event)
        assertTrue(json.contains("\"capture_session_id\":\"6078e44f-4d34-424a-af6d-fe2ad886ae84\""))
        assertTrue(json.contains("\"schema_version\":\"1.0\""))
        assertFalse(json.contains("captureSessionId"))
    }
}
