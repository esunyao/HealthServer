package cn.esuny.contracts.integration.v1

import com.fasterxml.jackson.databind.ObjectMapper
import kotlin.test.Test
import kotlin.test.assertContains
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AnalysisReviewRequiredContractTest {
    @Test
    fun `review event schema and asyncapi use the shared logical type`() {
        val schema = requireNotNull(javaClass.getResource("/schema/nutrition-analysis-review-required-v1.schema.json")).readText()
        val asyncApi = requireNotNull(javaClass.getResource("/asyncapi/nutrition-analysis-v1.yaml")).readText()
        val root = ObjectMapper().readTree(schema)

        assertEquals(NutritionEventTypes.ANALYSIS_REVIEW_REQUIRED, root.path("properties").path("event_type").path("const").asText())
        assertEquals("meal", root.path("properties").path("aggregate_type").path("const").asText())
        val requiredEnvelope = root.path("required").map { it.asText() }
        assertTrue(requiredEnvelope.containsAll(listOf("event_id", "event_type", "payload", "subject_id", "aggregate_id")))
        val requiredPayload = root.path("properties").path("payload").path("required").map { it.asText() }
        assertTrue(requiredPayload.containsAll(listOf("task_id", "capture_session_id", "meal_id", "reason_code", "message", "retryable")))
        assertContains(schema, "\"pattern\": \"^[A-Z0-9_]{1,64}$\"")
        assertContains(schema, "\"const\": false")
        assertContains(asyncApi, NutritionEventTypes.ANALYSIS_REVIEW_REQUIRED)
        assertContains(asyncApi, "nutrition-analysis-review-required-v1.schema.json")
        assertFalse(asyncApi.contains("agent-protocol"))
    }
}
