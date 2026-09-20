package cn.esuny.healthmind.interfaces.mcp

import cn.esuny.healthmind.application.port.out.InternalContextPort
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.database.ToolInvocationRepository
import cn.esuny.healthmind.infrastructure.http.CaptureImageContentLoader
import cn.esuny.healthmind.infrastructure.http.CaptureImageFetchException
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import cn.esuny.healthmind.infrastructure.json.JsonSchemaService
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import io.modelcontextprotocol.spec.McpSchema
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.security.core.authority.SimpleGrantedAuthority
import org.springframework.security.core.context.SecurityContextHolder
import org.springframework.security.oauth2.jwt.Jwt
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken
import tools.jackson.databind.ObjectMapper
import java.util.Base64
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class HealthMindMcpToolsTest {
    private val repository = mockk<ToolInvocationRepository>(relaxed = true)
    private val contexts = mockk<InternalContextPort>()
    private val schemas = mockk<JsonSchemaService>(relaxed = true)
    private val images = mockk<CaptureImageContentLoader>()
    private val canonicalJson = CanonicalJson(ObjectMapper())
    private val taskId = UUID.randomUUID()
    private val attemptId = UUID.randomUUID()
    private val invocation = invocation()

    @BeforeEach
    fun authenticate() {
        val jwt = Jwt.withTokenValue("test-token")
            .header("alg", "none")
            .subject(UUID.randomUUID().toString())
            .claim("azp", "dify-healthmind")
            .build()
        SecurityContextHolder.getContext().authentication = JwtAuthenticationToken(
            jwt,
            listOf(SimpleGrantedAuthority("SCOPE_capture.read")),
        )
        every { repository.authorizeAndStart(any(), any(), any(), any(), any()) } returns invocation
    }

    @AfterEach
    fun clearAuthentication() = SecurityContextHolder.clearContext()

    @Test
    fun `capture context returns image content and structured metadata without text`() {
        val context = canonicalJson.parse(
            """{"capture_session_id":"capture-1","meal_id":42,"image_urls":[]}""",
        )
        val imageBytes = byteArrayOf(1, 2, 3)
        val image = McpSchema.ImageContent.builder(
            Base64.getEncoder().encodeToString(imageBytes),
            "image/jpeg",
        ).build()
        every { contexts.getCaptureContext(invocation.grant) } returns context
        every { images.load(context) } returns listOf(image)

        val result = tools().captureContext(taskId.toString(), attemptId.toString())

        assertEquals(listOf(image), result.content())
        assertTrue(result.content().none { it is McpSchema.TextContent })
        assertEquals(42, (result.structuredContent() as Map<*, *>)["meal_id"])
        verify(exactly = 1) { repository.succeed(invocation, canonicalJson.sha256(context)) }
    }

    @Test
    fun `image failure uses capture image failure code and does not succeed`() {
        val context = canonicalJson.parse("""{"image_urls":[]}""")
        every { contexts.getCaptureContext(invocation.grant) } returns context
        every { images.load(context) } throws CaptureImageFetchException("safe summary")

        assertFailsWith<CaptureImageFetchException> {
            tools().captureContext(taskId.toString(), attemptId.toString())
        }

        verify(exactly = 1) { repository.fail(invocation, "CAPTURE_IMAGE_FETCH_FAILED") }
        verify(exactly = 0) { repository.succeed(any(), any()) }
    }

    @Test
    fun `nutrition context remains canonical JSON text`() {
        val context = canonicalJson.parse("""{"b":2,"a":1}""")
        every { contexts.getNutritionContext(invocation.grant) } returns context

        val result = tools().nutritionContext(taskId.toString(), attemptId.toString())

        assertEquals("""{"a":1,"b":2}""", result)
    }

    private fun tools() = HealthMindMcpTools(
        repository,
        contexts,
        canonicalJson,
        schemas,
        HealthMindProperties(
            oauth = HealthMindProperties.OAuth(allowedDifyClientId = "dify-healthmind"),
        ),
        images,
    )

    private fun invocation(): ToolInvocationRepository.StartedInvocation {
        val grant = ToolInvocationRepository.ToolGrant(
            taskId = taskId,
            attemptId = attemptId,
            subjectId = UUID.randomUUID(),
            traceId = "trace-1",
            releaseId = UUID.randomUUID(),
            captureSessionId = UUID.randomUUID(),
            mealId = 42,
            toolId = UUID.randomUUID(),
            requestSchemaVersion = "1.0",
            responseSchemaVersion = "1.0",
            requestSchema = "{}",
            responseSchema = "{}",
            allowedScope = "capture.read",
            maxCalls = 1,
            callCount = 0,
        )
        return ToolInvocationRepository.StartedInvocation(UUID.randomUUID(), grant)
    }
}
