package cn.esuny.healthmind.application.service

import cn.esuny.healthmind.application.port.out.AgentRunPort
import cn.esuny.healthmind.application.port.out.AgentRunState
import cn.esuny.healthmind.domain.task.AgentRunResult
import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.domain.task.TaskExecutionException
import cn.esuny.healthmind.infrastructure.database.TaskCommandRepository
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import cn.esuny.healthmind.infrastructure.json.JsonSchemaService
import io.micrometer.core.instrument.simple.SimpleMeterRegistry
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.junit.jupiter.api.Test
import tools.jackson.databind.ObjectMapper
import java.util.UUID

class TaskExecutionServiceTest {
    private val repository = mockk<TaskCommandRepository>(relaxed = true)
    private val agent = mockk<AgentRunPort>()
    private val canonical = CanonicalJson(ObjectMapper())
    private val service = TaskExecutionService(repository, agent, JsonSchemaService(canonical), canonical, SimpleMeterRegistry())

    @Test
    fun `submits an unsubmitted attempt and stores the returned run id`() {
        val command = command()
        val runId = UUID.randomUUID()
        every { repository.claimDue() } returns command
        every { agent.start(command) } returns runId

        service.advanceNext()

        verify(exactly = 1) { agent.start(command) }
        verify(exactly = 1) { repository.attachRun(command, runId) }
        verify(exactly = 0) { repository.fail(any(), any(), any(), any()) }
    }

    @Test
    fun `transient submission error keeps the attempt running for idempotent retry`() {
        val command = command()
        every { repository.claimDue() } returns command
        every { agent.start(command) } throws TaskExecutionException("AGENT_UNAVAILABLE", FailureCategory.TRANSIENT, "offline")

        service.advanceNext()

        verify(exactly = 0) { repository.fail(any(), any(), any(), any()) }
        verify(exactly = 0) { repository.attachRun(any(), any()) }
        verify(exactly = 1) { repository.schedulePoll(command) }
    }

    @Test
    fun `active run is rescheduled without writing a result`() {
        val command = command().copy(agentRunId = UUID.randomUUID())
        every { repository.claimDue() } returns command
        every { agent.inspect(command) } returns AgentRunState.Active

        service.advanceNext()

        verify(exactly = 1) { repository.schedulePoll(command) }
        verify(exactly = 0) { repository.complete(any(), any(), any()) }
    }

    @Test
    fun `successful run persists result after validating the schema`() {
        val runId = UUID.randomUUID()
        val command = command().copy(agentRunId = runId)
        val result = AgentRunResult(runId, """{"overall_confidence":0.9,"items":[]}""")
        every { repository.claimDue() } returns command
        every { agent.inspect(command) } returns AgentRunState.Succeeded(result)

        service.advanceNext()

        verify(exactly = 1) { repository.complete(command, result, any()) }
        verify(exactly = 0) { repository.fail(any(), any(), any(), any()) }
    }

    @Test
    fun `review output emits a failure instead of a nutrition result`() {
        val runId = UUID.randomUUID()
        val command = command().copy(agentRunId = runId)
        val result = AgentRunResult(runId, """{"status":"needs_review","reason_code":"IMAGE_UNAVAILABLE","message":"no image"}""")
        every { repository.claimDue() } returns command
        every { agent.inspect(command) } returns AgentRunState.Succeeded(result)

        service.advanceNext()

        verify(exactly = 1) { repository.fail(command, any(), FailureCategory.PERMANENT, "AGENT_NEEDS_REVIEW") }
        verify(exactly = 0) { repository.complete(any(), any(), any()) }
    }

    @Test
    fun `malformed agent output never becomes a successful nutrition result`() {
        val runId = UUID.randomUUID()
        val command = command().copy(agentRunId = runId)
        every { repository.claimDue() } returns command
        every { agent.inspect(command) } returns AgentRunState.Succeeded(AgentRunResult(runId, "not-json"))

        service.advanceNext()

        verify(exactly = 1) { repository.fail(command, any(), FailureCategory.CONTRACT, "AGENT_OUTPUT_INVALID") }
        verify(exactly = 0) { repository.complete(any(), any(), any()) }
    }

    private fun command() = TaskExecution(
        taskId = UUID.randomUUID(), attemptId = UUID.randomUUID(), attemptNo = 1, maxAttempts = 3,
        lockVersion = 1, subjectId = null, aggregateType = "meal", aggregateId = "42",
        captureSessionId = UUID.randomUUID(), mealId = 42, traceId = "trace-1",
        releaseId = UUID.randomUUID(), agentDeploymentKey = "meal-v1", agentAssistantId = "meal-analysis",
        agentArtifactSha256 = "a".repeat(64), outputSchemaVersion = "1.0", outputSchema = "{}", timeoutSeconds = 120,
    )
}
