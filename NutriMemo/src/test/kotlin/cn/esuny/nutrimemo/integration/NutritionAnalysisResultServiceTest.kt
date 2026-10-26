package cn.esuny.nutrimemo.integration

import cn.esuny.nutrimemo.model.MealAnalysisReportRecord
import cn.esuny.nutrimemo.model.NutrientDefinition
import cn.esuny.nutrimemo.persistence.NutriRepository
import cn.esuny.nutrimemo.service.SnowflakeIdGenerator
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.transaction.annotation.Transactional
import tools.jackson.databind.ObjectMapper
import java.math.BigDecimal
import java.time.LocalDate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class NutritionAnalysisResultServiceTest {
    private val inbox = mockk<NutritionResultRepository>(relaxed = true)
    private val nutri = mockk<NutriRepository>(relaxed = true)
    private val ids = mockk<SnowflakeIdGenerator>(relaxed = true)
    private val json = CanonicalEventJson(ObjectMapper())
    private val service = NutritionAnalysisResultService(inbox, nutri, ids, json)
    private val meal = NutritionResultRepository.ResultMeal(
        mealId = 42,
        captureSessionId = SESSION_UUID,
        userId = SUBJECT_UUID,
        localDate = LocalDate.parse("2026-10-26"),
        analysisStatus = "analysing",
        status = "active",
    )

    @BeforeEach
    fun setUp() {
        every { inbox.lockMeal(SESSION_UUID, 42) } returns meal
        every { inbox.startInbox(any(), any(), any()) } returns true
        every { inbox.hasManualOrCorrectedItems(42) } returns false
    }

    @Test
    fun `duplicate event id is ignored after inbox rejects it`() {
        every { inbox.startInbox(any(), any(), any()) } returns false

        service.process(completedEvent())

        verify(exactly = 0) { inbox.lockMeal(any(), any()) }
        verify(exactly = 0) { inbox.completeInbox(any()) }
        verify(exactly = 0) { inbox.saveReport(any()) }
    }

    @Test
    fun `unrecoverable result exceptions are committed before DLT propagation`() {
        val transaction = service.javaClass
            .getMethod("process", String::class.java)
            .getAnnotation(Transactional::class.java)

        assertTrue(transaction.noRollbackFor.contains(UnrecoverableResultEventException::class))
    }

    @Test
    fun `completed event persists report and AI writeback`() {
        val report = slot<MealAnalysisReportRecord>()
        every { inbox.saveReport(capture(report)) } returns true
        every { nutri.nutrientsByCodes(setOf("ENERGY_KCAL")) } returns listOf(
            NutrientDefinition(1001, "ENERGY_KCAL", "能量", "kcal", true),
        )
        every { ids.nextId() } returnsMany listOf(100L, 200L)

        service.process(completedEvent())

        assertEquals("completed", report.captured.status)
        assertEquals(UUID.fromString(TASK_ID), report.captured.taskId)
        assertEquals(BigDecimal("0.86"), report.captured.overallConfidence)
        assertEquals(1, report.captured.resultVersion)
        verify(exactly = 1) { nutri.replaceAiItems(42, any(), any()) }
        verify(exactly = 1) { inbox.markCompleted(meal, true) }
        verify(exactly = 1) { inbox.completeInbox(UUID.fromString(EVENT_ID)) }
    }

    @Test
    fun `failed event terminalizes an analysing meal and stores reason`() {
        val report = slot<MealAnalysisReportRecord>()
        every { inbox.saveReport(capture(report)) } returns true

        service.process(failedEvent())

        assertEquals("failed", report.captured.status)
        assertEquals("AGENT_RUN_FAILED", report.captured.reasonCode)
        assertEquals("The model run failed", report.captured.reasonMessage)
        verify(exactly = 1) { inbox.markFailed(meal) }
        verify(exactly = 0) { inbox.markNeedsReview(any()) }
    }

    @Test
    fun `review required event terminalizes an analysing meal without technical failure`() {
        val report = slot<MealAnalysisReportRecord>()
        every { inbox.saveReport(capture(report)) } returns true

        service.process(reviewEvent())

        assertEquals("needs_review", report.captured.status)
        assertEquals("IMAGE_UNAVAILABLE", report.captured.reasonCode)
        assertEquals("No confirmed image can be analysed", report.captured.reasonMessage)
        verify(exactly = 1) { inbox.markNeedsReview(meal) }
        verify(exactly = 0) { inbox.markFailed(any()) }
    }

    @Test
    fun `older event cannot mutate a newer terminal state`() {
        every { inbox.saveReport(any()) } returns false

        service.process(reviewEvent(occurredAt = "2026-08-01T00:00:00Z"))

        verify(exactly = 0) { inbox.markNeedsReview(any()) }
        verify(exactly = 0) { inbox.markFailed(any()) }
        verify(exactly = 0) { inbox.markCompleted(any(), any()) }
        verify(exactly = 1) { inbox.completeInbox(UUID.fromString(EVENT_ID)) }
    }

    @Test
    fun `older completed event cannot replace newer AI items`() {
        every { inbox.saveReport(any()) } returns false
        every { nutri.nutrientsByCodes(setOf("ENERGY_KCAL")) } returns listOf(
            NutrientDefinition(1001, "ENERGY_KCAL", "能量", "kcal", true),
        )

        service.process(completedEvent())

        verify(exactly = 0) { nutri.replaceAiItems(any(), any(), any()) }
        verify(exactly = 0) { inbox.markCompleted(any(), any()) }
        verify(exactly = 1) { inbox.completeInbox(UUID.fromString(EVENT_ID)) }
    }

    @Test
    fun `manual data wins while business meal is terminalized as completed`() {
        every { inbox.saveReport(any()) } returns true
        every { inbox.hasManualOrCorrectedItems(42) } returns true
        every { nutri.nutrientsByCodes(setOf("ENERGY_KCAL")) } returns listOf(
            NutrientDefinition(1001, "ENERGY_KCAL", "能量", "kcal", true),
        )

        service.process(completedEvent())

        verify(exactly = 1) { inbox.markCompleted(meal, true) }
        verify(exactly = 0) { nutri.replaceAiItems(any(), any(), any()) }
    }

    @Test
    fun `manual data wins when invalid result is terminalized`() {
        every { inbox.saveReport(any()) } returns true
        every { inbox.hasManualOrCorrectedItems(42) } returns true

        assertFailsWith<UnrecoverableResultEventException> {
            service.process(completedEvent(schemaVersion = "2.0"))
        }

        verify(exactly = 1) { inbox.markCompleted(meal, true) }
        verify(exactly = 0) { inbox.markFailed(any()) }
    }

    @Test
    fun `event id reused with different content enters DLT without mutating meal`() {
        every { inbox.startInbox(any(), any(), any()) } throws UnrecoverableResultEventException(
            "EVENT_IDEMPOTENCY_CONFLICT",
            "Integration event ID was reused with different content",
        )

        val exception = assertFailsWith<UnrecoverableResultEventException> {
            service.process(completedEvent())
        }

        assertEquals("EVENT_IDEMPOTENCY_CONFLICT", exception.reasonCode)
        verify(exactly = 0) { inbox.lockMeal(any(), any()) }
        verify(exactly = 0) { inbox.saveReport(any()) }
        verify(exactly = 1) {
            inbox.recordDeadLetter(
                UUID.fromString(EVENT_ID),
                "nutrition.analysis.completed.v1",
                null,
                any(),
                any(),
                "EVENT_IDEMPOTENCY_CONFLICT",
                "Integration event ID was reused with different content",
            )
        }
    }

    @Test
    fun `invalid event identifier still terminalizes a locatable meal before DLT`() {
        val report = slot<MealAnalysisReportRecord>()
        every { inbox.saveReport(capture(report)) } returns true

        val exception = assertFailsWith<UnrecoverableResultEventException> {
            service.process(completedEvent(eventId = "not-a-uuid"))
        }

        assertEquals("INVALID_EVENT_ID", exception.reasonCode)
        assertEquals("failed", report.captured.status)
        assertEquals("INVALID_EVENT_ID", report.captured.reasonCode)
        verify(exactly = 0) { inbox.startInbox(any(), any(), any()) }
        verify(exactly = 1) { inbox.markFailed(meal) }
        verify(exactly = 1) {
            inbox.recordDeadLetter(
                null,
                "nutrition.analysis.completed.v1",
                42,
                any(),
                any(),
                "INVALID_EVENT_ID",
                "INVALID_EVENT_ID",
            )
        }
    }

    @Test
    fun `locatable invalid event persists failed terminal state before entering DLT`() {
        val report = slot<MealAnalysisReportRecord>()
        every { inbox.saveReport(capture(report)) } returns true

        val exception = assertFailsWith<UnrecoverableResultEventException> {
            service.process(completedEvent(schemaVersion = "2.0"))
        }

        assertEquals("EVENT_CONTRACT_INVALID", exception.reasonCode)
        assertEquals("failed", report.captured.status)
        assertEquals("EVENT_CONTRACT_INVALID", report.captured.reasonCode)
        verify(exactly = 1) { inbox.markFailed(meal) }
        verify(exactly = 1) { inbox.failInbox(UUID.fromString(EVENT_ID), "UNSUPPORTED_SCHEMA_VERSION") }
        verify(exactly = 1) {
            inbox.recordDeadLetter(
                UUID.fromString(EVENT_ID),
                "nutrition.analysis.completed.v1",
                42,
                any(),
                any(),
                "EVENT_CONTRACT_INVALID",
                "UNSUPPORTED_SCHEMA_VERSION",
            )
        }
    }

    @Test
    fun `unparseable event is persisted for DLT without creating an inbox row`() {
        val digest = slot<String>()

        val exception = assertFailsWith<UnrecoverableResultEventException> {
            service.process("not-json")
        }

        assertEquals("UNPARSEABLE_EVENT", exception.reasonCode)
        verify(exactly = 0) { inbox.startInbox(any(), any(), any()) }
        verify(exactly = 1) {
            inbox.recordDeadLetter(
                null,
                null,
                null,
                capture(digest),
                "not-json",
                "UNPARSEABLE_EVENT",
                "Result event is not valid JSON",
            )
        }
        assertTrue(digest.captured.matches(Regex("^[0-9a-f]{64}$")))
    }

    @Test
    fun `unlocatable event is audited and never completes inbox`() {
        every { inbox.lockMeal(SESSION_UUID, 42) } returns null

        val exception = assertFailsWith<UnrecoverableResultEventException> {
            service.process(completedEvent())
        }

        assertEquals("MEAL_NOT_FOUND", exception.reasonCode)
        verify(exactly = 1) { inbox.startInbox(UUID.fromString(EVENT_ID), any(), any()) }
        verify(exactly = 1) { inbox.failInbox(UUID.fromString(EVENT_ID), "Result event does not match a locked meal") }
        verify(exactly = 1) {
            inbox.recordDeadLetter(
                UUID.fromString(EVENT_ID),
                "nutrition.analysis.completed.v1",
                null,
                any(),
                any(),
                "MEAL_NOT_FOUND",
                "Result event does not match a locked meal",
            )
        }
    }

    @Test
    fun `canonical digest ignores object property order before inbox idempotency`() {
        every { inbox.startInbox(any(), any(), any()) } returns false
        val digests = mutableListOf<String>()

        service.process(
            """{"event_id":"$EVENT_ID","event_type":"nutrition.analysis.completed.v1","payload":{"meal_id":42,"task_id":"$TASK_ID","capture_session_id":"$SESSION_ID","result_version":1,"overall_confidence":0.86,"items":[]},"occurred_at":"2026-10-26T12:00:00Z","producer":"HealthMind","trace_id":"trace-1","subject_id":"$SUBJECT_ID","aggregate_type":"meal","aggregate_id":"42","schema_version":"1.0"}""",
        )
        service.process(
            """{"event_id":"$EVENT_ID","event_type":"nutrition.analysis.completed.v1","occurred_at":"2026-10-26T12:00:00Z","producer":"HealthMind","trace_id":"trace-1","subject_id":"$SUBJECT_ID","aggregate_type":"meal","aggregate_id":"42","schema_version":"1.0","payload":{"task_id":"$TASK_ID","capture_session_id":"$SESSION_ID","meal_id":42,"result_version":1,"overall_confidence":0.86,"items":[]}}""",
        )

        verify(exactly = 2) { inbox.startInbox(UUID.fromString(EVENT_ID), any(), capture(digests)) }
        assertEquals(digests[0], digests[1])
    }

    private fun completedEvent(schemaVersion: String = "1.0", eventId: String = EVENT_ID) =
        """{"event_id":"$eventId","event_type":"nutrition.analysis.completed.v1","occurred_at":"2026-10-26T12:00:00Z","producer":"HealthMind","trace_id":"trace-1","subject_id":"$SUBJECT_ID","aggregate_type":"meal","aggregate_id":"42","schema_version":"$schemaVersion","payload":{"task_id":"$TASK_ID","capture_session_id":"$SESSION_ID","meal_id":42,"result_version":1,"overall_confidence":0.86,"items":[{"name":"米饭","weight_grams":150,"confidence":0.8,"nutrients":[{"code":"ENERGY_KCAL","value":174}]}]}}"""

    private fun failedEvent() =
        """{"event_id":"$EVENT_ID","event_type":"nutrition.analysis.failed.v1","occurred_at":"2026-10-26T12:00:00Z","producer":"HealthMind","trace_id":"trace-1","subject_id":"$SUBJECT_ID","aggregate_type":"meal","aggregate_id":"42","schema_version":"1.0","payload":{"task_id":"$TASK_ID","capture_session_id":"$SESSION_ID","meal_id":42,"error_code":"AGENT_RUN_FAILED","failure_category":"permanent","retryable":false,"error_summary":"The model run failed"}}"""

    private fun reviewEvent(occurredAt: String = "2026-10-26T12:00:00Z") =
        """{"event_id":"$EVENT_ID","event_type":"nutrition.analysis.review_required.v1","occurred_at":"$occurredAt","producer":"HealthMind","trace_id":"trace-1","subject_id":"$SUBJECT_ID","aggregate_type":"meal","aggregate_id":"42","schema_version":"1.0","payload":{"task_id":"$TASK_ID","capture_session_id":"$SESSION_ID","meal_id":42,"reason_code":"IMAGE_UNAVAILABLE","message":"No confirmed image can be analysed","retryable":false}}"""

    companion object {
        const val EVENT_ID = "68a8e352-e4bd-48dc-b886-d9257dfc62b2"
        const val TASK_ID = "b03e399d-b160-48ed-b9fa-9de1a22cbb19"
        const val SESSION_ID = "394898bc-dca6-42f9-9423-4482db2e6329"
        const val SUBJECT_ID = "506f58ad-4727-490f-b4a2-877f42811c1e"
        val SESSION_UUID: UUID = UUID.fromString(SESSION_ID)
        val SUBJECT_UUID: UUID = UUID.fromString(SUBJECT_ID)
    }
}
