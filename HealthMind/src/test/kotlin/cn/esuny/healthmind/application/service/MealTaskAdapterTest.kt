package cn.esuny.healthmind.application.service

import cn.esuny.healthmind.application.port.out.TaskOutcomePort
import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import org.junit.jupiter.api.Test
import tools.jackson.databind.ObjectMapper
import java.util.UUID
import kotlin.test.assertEquals

class MealTaskAdapterTest {
    private val mapper = ObjectMapper()
    private val adapter = MealTaskAdapter(mapper, CanonicalJson(mapper), HealthMindProperties())

    @Test
    fun `review event is non retryable and uses the shared destination`() {
        val command = command()
        val event = adapter.reviewRequiredEvent(command, "IMAGE_UNAVAILABLE", "No confirmed image")

        assertEquals("nutrition.analysis.review_required.v1", event.eventType)
        assertEquals("nutrition-analysis-review-required", event.destinationKey)
        assertEquals("nutrition.analysis.review_required.v1", event.payload.path("event_type").asString())
        assertEquals("IMAGE_UNAVAILABLE", event.payload.path("payload").path("reason_code").asString())
        assertEquals(false, event.payload.path("payload").path("retryable").booleanValue())
    }

    private fun command() = TaskExecution(
        taskId = UUID.randomUUID(),
        attemptId = UUID.randomUUID(),
        attemptNo = 1,
        maxAttempts = 3,
        lockVersion = 1,
        taskTypeCode = MealTaskAdapter.MEAL_ANALYSIS_TASK_TYPE,
        subjectId = UUID.randomUUID(),
        aggregateType = "meal",
        aggregateId = "42",
        contextManifest = """{"capture_session_id":"${UUID.randomUUID()}","meal_id":42}""",
        traceId = "trace-1",
        releaseId = UUID.randomUUID(),
        agentDeploymentKey = "meal-v1",
        agentAssistantId = "meal-analysis",
        agentArtifactSha256 = "a".repeat(64),
        outputSchemaVersion = "1.0",
        outputSchema = "{}",
        timeoutSeconds = 120,
    )
}
