package cn.esuny.nutrimemo.integration

import cn.esuny.nutrimemo.persistence.NutriRepository
import cn.esuny.nutrimemo.service.SnowflakeIdGenerator
import io.mockk.Runs
import io.mockk.every
import io.mockk.just
import io.mockk.mockk
import io.mockk.verify
import org.junit.jupiter.api.Test
import tools.jackson.databind.ObjectMapper
import java.util.UUID
import kotlin.test.assertEquals

class NutritionAnalysisResultServiceTest {
    private val inbox = mockk<NutritionResultRepository>()
    private val nutri = mockk<NutriRepository>()
    private val ids = mockk<SnowflakeIdGenerator>()
    private val json = CanonicalEventJson(ObjectMapper())
    private val service = NutritionAnalysisResultService(inbox, nutri, ids, json)

    @Test
    fun `duplicate event id is ignored after inbox rejects it`() {
        every { inbox.startInbox(any(), any(), any()) } returns false

        service.process(event(schemaVersion = "1.0"))

        verify(exactly = 0) { inbox.lockMeal(any(), any()) }
        verify(exactly = 0) { inbox.completeInbox(any()) }
    }

    @Test
    fun `unsupported schema version is recorded as failed inbox`() {
        val eventId = UUID.fromString(EVENT_ID)
        every { inbox.startInbox(eventId, "nutrition.analysis.completed.v1", any()) } returns true
        every { inbox.failInbox(eventId, "UNSUPPORTED_SCHEMA_VERSION") } just Runs

        service.process(event(schemaVersion = "2.0"))

        verify(exactly = 1) { inbox.failInbox(eventId, "UNSUPPORTED_SCHEMA_VERSION") }
        verify(exactly = 0) { inbox.lockMeal(any(), any()) }
    }

    @Test
    fun `canonical digest is stable across object property order`() {
        val first = json.digest(json.parse("""{"b":2,"a":1}"""))
        val second = json.digest(json.parse("""{"a":1,"b":2}"""))

        assertEquals(first, second)
    }

    private fun event(schemaVersion: String) =
        """{"event_id":"$EVENT_ID","event_type":"nutrition.analysis.completed.v1","occurred_at":"2026-08-29T00:00:00Z","producer":"HealthMind","trace_id":"trace-1","subject_id":"506f58ad-4727-490f-b4a2-877f42811c1e","aggregate_type":"meal","aggregate_id":"42","schema_version":"$schemaVersion","payload":{"task_id":"b03e399d-b160-48ed-b9fa-9de1a22cbb19","capture_session_id":"394898bc-dca6-42f9-9423-4482db2e6329","meal_id":42,"result_version":1,"overall_confidence":0.9,"items":[]}}"""

    companion object {
        const val EVENT_ID = "68a8e352-e4bd-48dc-b886-d9257dfc62b2"
    }
}
