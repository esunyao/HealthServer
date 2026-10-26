package cn.esuny.healthmind.infrastructure.http

import cn.esuny.healthmind.application.service.MealTaskAdapter
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.database.ToolInvocationRepository
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

class InternalContextClientTest {
    private val server = MockWebServer()
    private val tokens = mockk<ClientCredentialsTokenProvider>()
    private val adapter = mockk<MealTaskAdapter>()

    @AfterEach
    fun close() = server.close()

    @Test
    fun `meal notes capability follows the pinned tool response schema version`() {
        server.start()
        repeat(2) { server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("""{"ok":true}""")) }
        every { tokens.token(any<HealthMindProperties.OAuth.Client>()) } returns "test-token"
        every { adapter.context(any()) } returns MealTaskAdapter.MealContext(SESSION_ID, 42)

        getCaptureContext(responseSchemaVersion = "1.0")
        getCaptureContext(responseSchemaVersion = "1.1")

        val legacy = server.takeRequest()
        val upgraded = server.takeRequest()
        assertEquals(false, ObjectMapper().readTree(legacy.body.readUtf8()).path("include_meal_notes").booleanValue())
        assertEquals(true, ObjectMapper().readTree(upgraded.body.readUtf8()).path("include_meal_notes").booleanValue())
    }

    private fun getCaptureContext(responseSchemaVersion: String) {
        client().getCaptureContext(
            ToolInvocationRepository.ToolGrant(
                taskId = TASK_ID,
                attemptId = ATTEMPT_ID,
                taskTypeCode = MealTaskAdapter.MEAL_ANALYSIS_TASK_TYPE,
                subjectId = SUBJECT_ID,
                traceId = "trace-1",
                releaseId = RELEASE_ID,
                contextManifest = """{"capture_session_id":"$SESSION_ID","meal_id":42}""",
                toolId = TOOL_ID,
                requestSchemaVersion = "1.0",
                responseSchemaVersion = responseSchemaVersion,
                requestSchema = "{}",
                responseSchema = "{}",
                allowedScope = "scope",
                maxCalls = 10,
                callCount = 0,
            ),
        )
    }

    private fun client(): InternalContextClient {
        val defaults = HealthMindProperties()
        val properties = defaults.copy(
            oauth = defaults.oauth.copy(
                nutrimemo = defaults.oauth.nutrimemo.copy(baseUrl = server.url("/").toString()),
            ),
        )
        return InternalContextClient(RestClient.builder(), tokens, properties, adapter)
    }

    private companion object {
        val TASK_ID: UUID = UUID.fromString("11111111-1111-4111-8111-111111111111")
        val ATTEMPT_ID: UUID = UUID.fromString("22222222-2222-4222-8222-222222222222")
        val SUBJECT_ID: UUID = UUID.fromString("33333333-3333-4333-8333-333333333333")
        val RELEASE_ID: UUID = UUID.fromString("44444444-4444-4444-8444-444444444444")
        val SESSION_ID: UUID = UUID.fromString("55555555-5555-4555-8555-555555555555")
        val TOOL_ID: UUID = UUID.fromString("66666666-6666-4666-8666-666666666666")
    }
}
