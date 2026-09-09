package cn.esuny.healthmind.infrastructure.dify

import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.domain.task.TaskExecutionException
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import tools.jackson.databind.ObjectMapper
import java.util.UUID
import java.time.Duration
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith

class DifyWorkflowClientTest {
    private val server = MockWebServer()

    @AfterEach
    fun close() = server.close()

    @Test
    fun `runs pinned workflow id with task pseudonym`() {
        server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(
            """{"workflow_run_id":"run-1","data":{"id":"run-1","workflow_id":"wf-1","status":"succeeded","outputs":{"result":{"overall_confidence":0.9,"items":[]}}}}""",
        ))
        server.start()
        val properties = HealthMindProperties(
            dify = HealthMindProperties.Dify(
                baseUrl = server.url("/v1").toString().trimEnd('/'),
                appKeys = mapOf("app-1" to "secret-key"),
            ),
        )
        val client = DifyWorkflowClient(RestClient.builder(), ObjectMapper(), properties)
        val result = client.run(command())

        val request = server.takeRequest()
        assertEquals("/v1/workflows/wf-1/run", request.path)
        assertEquals("Bearer secret-key", request.getHeader("Authorization"))
        assertFalse(request.body.readUtf8().contains("subject_id"))
        assertEquals("run-1", result.workflowRunId)
    }

    @Test
    fun `classifies a read timeout as retryable timeout`() {
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("{}")
                .setBodyDelay(500, TimeUnit.MILLISECONDS),
        )
        server.start()
        val client = DifyWorkflowClient(
            RestClient.builder(),
            ObjectMapper(),
            HealthMindProperties(
                dify = HealthMindProperties.Dify(
                    baseUrl = server.url("/v1").toString().trimEnd('/'),
                    appKeys = mapOf("app-1" to "test-only-key"),
                    readTimeout = Duration.ofMillis(50),
                ),
            ),
        )

        val exception = assertFailsWith<TaskExecutionException> { client.run(command()) }

        val causeChain = generateSequence<Throwable>(exception) { it.cause }
            .joinToString(" -> ") { "${it.javaClass.name}: ${it.message}" }
        assertEquals("DIFY_TIMEOUT", exception.code, causeChain)
        assertEquals("timeout", exception.category.wireValue)
    }

    @Test
    fun `retains Dify workflow failure detail`() {
        server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(
            """{"data":{"workflow_id":"wf-1","status":"failed","error":"MCP tool nutrimemo.capture_context.get failed"}}""",
        ))
        server.start()
        val client = DifyWorkflowClient(
            RestClient.builder(),
            ObjectMapper(),
            HealthMindProperties(dify = HealthMindProperties.Dify(
                baseUrl = server.url("/v1").toString().trimEnd('/'),
                appKeys = mapOf("app-1" to "test-only-key"),
            )),
        )

        val exception = assertFailsWith<TaskExecutionException> { client.run(command()) }

        assertEquals("DIFY_WORKFLOW_FAILED", exception.code)
        assertEquals(
            "Dify workflow did not succeed (status=failed): MCP tool nutrimemo.capture_context.get failed",
            exception.message,
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
        difyAppId = "app-1",
        difyWorkflowId = "wf-1",
        difyWorkflowVersion = "release-1",
        outputSchemaVersion = "1.0",
        outputSchema = "{}",
        timeoutSeconds = 120,
    )
}
