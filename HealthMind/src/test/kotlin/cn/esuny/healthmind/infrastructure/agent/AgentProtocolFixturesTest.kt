package cn.esuny.healthmind.infrastructure.agent

import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.domain.task.TaskExecutionException
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.oauth.ClientCredentialsTokenProvider
import com.networknt.schema.SchemaRegistry
import com.networknt.schema.SpecificationVersion
import io.mockk.every
import io.mockk.mockk
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import tools.jackson.databind.JsonNode
import tools.jackson.databind.ObjectMapper
import tools.jackson.databind.node.ObjectNode
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class AgentProtocolFixturesTest {
    private val server = MockWebServer()
    private val mapper = ObjectMapper()
    private val tokens = mockk<ClientCredentialsTokenProvider>()
    private val registry = SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_2020_12)

    @AfterEach
    fun close() = server.close()

    @Test
    fun `shared request and response examples satisfy their JSON schemas`() {
        listOf(
            "thread-create-request",
            "thread-response",
            "run-create-request",
            "run-response",
        ).forEach { name ->
            val schema = fixture("$name.schema.json")
            val example = fixture("examples/$name.json")
            val errors = registry.getSchema(schema).validate(example)
            assertTrue(errors.isEmpty(), errors.toString())
        }
    }

    @Test
    fun `shared fixtures drive thread creation and idempotent reuse`() {
        server.start()
        repeat(2) {
            server.enqueue(jsonResponse(fixture("examples/thread-response.json")))
            server.enqueue(jsonResponse(fixture("examples/run-response.json")))
        }
        val client = client()

        assertEquals(fixture("examples/run-response.json").path("run_id").asString(), client.start(command()).toString())
        assertEquals(fixture("examples/run-response.json").path("run_id").asString(), client.start(command()).toString())

        repeat(2) {
            val threadRequest = server.takeRequest()
            assertEquals("/threads", threadRequest.path)
            assertEquals(fixture("examples/thread-create-request.json"), mapper.readTree(threadRequest.body.readUtf8()))
            val runRequest = server.takeRequest()
            assertEquals("/threads/${command().attemptId}/runs", runRequest.path)
            assertEquals(fixture("examples/run-create-request.json"), mapper.readTree(runRequest.body.readUtf8()))
        }
    }

    @Test
    fun `conflicting shared thread identity is rejected before run creation`() {
        server.start()
        val conflict = fixture("examples/thread-response.json") as ObjectNode
        (conflict.get("metadata") as ObjectNode).put("task_id", "99999999-9999-4999-8999-999999999999")
        server.enqueue(jsonResponse(conflict))

        val error = assertFailsWith<TaskExecutionException> { client().start(command()) }

        assertEquals("AGENT_THREAD_MISMATCH", error.code)
        assertEquals(1, server.requestCount)
    }

    @Test
    fun `thread can be rebuilt after a lost creation response`() {
        server.start()
        server.enqueue(MockResponse().setResponseCode(503))
        val first = assertFailsWith<TaskExecutionException> { client().start(command()) }
        assertTrue(first.safeToRetrySubmission)

        server.enqueue(jsonResponse(fixture("examples/thread-response.json")))
        server.enqueue(jsonResponse(fixture("examples/run-response.json")))
        val runId = client().start(command())

        assertEquals(fixture("examples/run-response.json").path("run_id").asString(), runId.toString())
        assertEquals("/threads", server.takeRequest().path)
        assertEquals("/threads", server.takeRequest().path)
        assertEquals("/threads/${command().attemptId}/runs", server.takeRequest().path)
    }

    private fun client(): AgentRunClient {
        every { tokens.token(any<HealthMindProperties.OAuth.Credentials>()) } returns "test-token"
        return AgentRunClient(
            RestClient.builder(),
            mapper,
            tokens,
            HealthMindProperties(
                agent = HealthMindProperties.Agent(
                    deployments = mapOf("meal-v1" to server.url("/").toString()),
                ),
            ),
        )
    }

    private fun command(): TaskExecution {
        val threadRequest = fixture("examples/thread-create-request.json")
        val runRequest = fixture("examples/run-create-request.json")
        return TaskExecution(
            taskId = UUID.fromString(threadRequest.path("metadata").path("task_id").asString()),
            attemptId = UUID.fromString(threadRequest.path("metadata").path("attempt_id").asString()),
            attemptNo = 1,
            maxAttempts = 3,
            lockVersion = 1,
            taskTypeCode = "nutrition.meal_analysis",
            subjectId = UUID.fromString("44444444-4444-4444-8444-444444444444"),
            aggregateType = "meal",
            aggregateId = "42",
            contextManifest = "{}",
            traceId = runRequest.path("input").path("trace_id").asString(),
            releaseId = UUID.fromString(runRequest.path("metadata").path("release_id").asString()),
            agentDeploymentKey = "meal-v1",
            agentAssistantId = runRequest.path("assistant_id").asString(),
            agentArtifactSha256 = runRequest.path("metadata").path("artifact_sha256").asString(),
            outputSchemaVersion = "1.0",
            outputSchema = "{}",
            timeoutSeconds = 120,
        )
    }

    private fun fixture(name: String): JsonNode = checkNotNull(javaClass.getResourceAsStream("/agent-protocol/v1/$name")).use {
        mapper.readTree(it)
    }

    private fun jsonResponse(body: JsonNode) = MockResponse()
        .setHeader("Content-Type", "application/json")
        .setBody(mapper.writeValueAsString(body))
}
