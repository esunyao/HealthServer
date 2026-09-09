package cn.esuny.healthmind.interfaces.messaging

import cn.esuny.healthmind.domain.task.ProductionWorkflowUnavailableException
import cn.esuny.healthmind.infrastructure.database.TaskCommandRepository
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.springframework.kafka.support.Acknowledgment
import tools.jackson.databind.json.JsonMapper
import java.time.Duration
import kotlin.test.Test
import kotlin.test.assertFailsWith

class NutritionCaptureReadyListenerTest {
    private val repository = mockk<TaskCommandRepository>()
    private val acknowledgment = mockk<Acknowledgment>(relaxed = true)
    private val listener = NutritionCaptureReadyListener(CanonicalJson(JsonMapper.builder().build()), repository)
    private val raw = """{
      "event_id":"11111111-1111-4111-8111-111111111111",
      "event_type":"nutrition.capture.ready.v1","occurred_at":"2026-09-09T00:00:00Z",
      "producer":"NutriMemo","trace_id":"test","subject_id":"22222222-2222-4222-8222-222222222222",
      "aggregate_type":"meal","aggregate_id":"123","schema_version":"1.0",
      "payload":{"capture_session_id":"33333333-3333-4333-8333-333333333333","meal_id":123}
    }"""

    @Test
    fun `missing production release defers without acknowledging or throwing`() {
        every { repository.acceptCaptureReady(any(), any(), any()) } throws ProductionWorkflowUnavailableException()
        listener.receive(raw, acknowledgment)
        verify(exactly = 1) { acknowledgment.nack(Duration.ofSeconds(30)) }
        verify(exactly = 0) { acknowledgment.acknowledge() }
    }

    @Test
    fun `successful or duplicate event is acknowledged`() {
        every { repository.acceptCaptureReady(any(), any(), any()) } returns null
        listener.receive(raw, acknowledgment)
        verify(exactly = 1) { acknowledgment.acknowledge() }
        verify(exactly = 0) { acknowledgment.nack(any<Duration>()) }
    }

    @Test
    fun `unexpected failure is not swallowed`() {
        every { repository.acceptCaptureReady(any(), any(), any()) } throws IllegalStateException("database unavailable")
        assertFailsWith<IllegalStateException> { listener.receive(raw, acknowledgment) }
        verify(exactly = 0) { acknowledgment.acknowledge() }
    }
}
