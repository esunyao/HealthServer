package cn.esuny.healthmind.infrastructure.agent

import cn.esuny.healthmind.application.port.out.AgentRunState
import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.domain.task.TaskExecutionException
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.oauth.ClientCredentialsTokenProvider
import io.mockk.every
import io.mockk.mockk
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import tools.jackson.databind.ObjectMapper
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse

class AgentRunClientTest {
    private val server = MockWebServer()
    private val mapper = ObjectMapper()
    private val tokens = mockk<ClientCredentialsTokenProvider>()

    @AfterEach
    fun close() = server.close()

    @Test
    fun `submits only task identifiers and pins the agent release`() {
        server.start()
        val command = command()
        val runId = UUID.randomUUID()
        server.enqueue(jsonResponse(run(runId, command, "pending")))
        val client = client()

        assertEquals(runId, client.start(command))

        val request = server.takeRequest()
        assertEquals("/runs", request.path)
        assertEquals("Bearer test-token", request.getHeader("Authorization"))
        assertEquals(command.attemptId.toString(), request.getHeader("Idempotency-Key"))
        val body = mapper.readTree(request.body.readUtf8())
        assertEquals(command.agentAssistantId, body.path("assistant_id").asString())
        assertEquals(command.taskId.toString(), body.path("input").path("task_id").asString())
        assertEquals(command.attemptId.toString(), body.path("input").path("attempt_id").asString())
        assertEquals(command.traceId, body.path("input").path("trace_id").asString())
        assertEquals(3, body.path("input").properties().size)
        assertFalse(body.toString().contains("subject_id"))
    }

    @Test
    fun `retrying an unacknowledged submission uses the same idempotency key`() {
        server.start()
        val command = command()
        val runId = UUID.randomUUID()
        server.enqueue(jsonResponse(run(runId, command, "pending")))
        server.enqueue(jsonResponse(run(runId, command, "pending")))
        val client = client()

        assertEquals(runId, client.start(command))
        assertEquals(runId, client.start(command))

        val first = server.takeRequest()
        val second = server.takeRequest()
        assertEquals(first.getHeader("Idempotency-Key"), second.getHeader("Idempotency-Key"))
        assertEquals(first.body.readUtf8(), second.body.readUtf8())
    }

    @Test
    fun `polls run and reads final output only after success`() {
        server.start()
        val runId = UUID.randomUUID()
        val command = command().copy(agentRunId = runId)
        server.enqueue(jsonResponse(run(runId, command, "running")))
        server.enqueue(jsonResponse(run(runId, command, "success")))
        server.enqueue(jsonResponse("""{"output":{"overall_confidence":0.9,"items":[]}}"""))
        val client = client()

        assertEquals(AgentRunState.Active, client.inspect(command))
        val completed = client.inspect(command) as AgentRunState.Succeeded

        assertEquals(runId, completed.result.runId)
        assertEquals(0.9, mapper.readTree(completed.result.outputJson).path("overall_confidence").asDouble())
        assertEquals("/runs/$runId", server.takeRequest().path)
        assertEquals("/runs/$runId", server.takeRequest().path)
        assertEquals("/runs/$runId/wait", server.takeRequest().path)
    }

    @Test
    fun `rejects a run not matching the pinned attempt and release`() {
        server.start()
        val command = command()
        server.enqueue(jsonResponse("""{"run_id":"${UUID.randomUUID()}","metadata":{}}"""))

        val error = assertFailsWith<TaskExecutionException> { client().start(command) }

        assertEquals("AGENT_IDENTITY_MISMATCH", error.code)
    }

    private fun client(): AgentRunClient {
        every { tokens.token(any<HealthMindProperties.OAuth.Credentials>()) } returns "test-token"
        return AgentRunClient(
            RestClient.builder(), mapper, tokens,
            HealthMindProperties(agent = HealthMindProperties.Agent(deployments = mapOf("meal-v1" to server.url("/").toString()))),
        )
    }

    private fun command() = TaskExecution(
        taskId = UUID.randomUUID(),
        attemptId = UUID.randomUUID(),
        attemptNo = 1,
        maxAttempts = 3,
        lockVersion = 1,
        subjectId = UUID.randomUUID(),
        aggregateType = "meal",
        aggregateId = "42",
        captureSessionId = UUID.randomUUID(),
        mealId = 42,
        traceId = "trace-1",
        releaseId = UUID.randomUUID(),
        agentDeploymentKey = "meal-v1",
        agentAssistantId = "meal-analysis",
        agentArtifactSha256 = "a".repeat(64),
        outputSchemaVersion = "1.0",
        outputSchema = "{}",
        timeoutSeconds = 120,
    )

    private fun run(runId: UUID, command: TaskExecution, status: String) = """
        {"run_id":"$runId","assistant_id":"${command.agentAssistantId}","status":"$status","metadata":{
            "task_id":"${command.taskId}","attempt_id":"${command.attemptId}","release_id":"${command.releaseId}",
            "artifact_sha256":"${command.agentArtifactSha256}"}}
    """.trimIndent()

    private fun jsonResponse(body: String) = MockResponse().setHeader("Content-Type", "application/json").setBody(body)
}
