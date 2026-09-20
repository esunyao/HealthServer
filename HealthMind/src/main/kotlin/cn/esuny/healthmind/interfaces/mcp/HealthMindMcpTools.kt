package cn.esuny.healthmind.interfaces.mcp

import cn.esuny.healthmind.application.port.out.InternalContextPort
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.database.ToolInvocationRepository
import cn.esuny.healthmind.infrastructure.http.CaptureImageContentLoader
import cn.esuny.healthmind.infrastructure.http.CaptureImageFetchException
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import cn.esuny.healthmind.infrastructure.json.JsonSchemaService
import io.modelcontextprotocol.spec.McpSchema
import org.springframework.ai.mcp.annotation.McpTool
import org.springframework.ai.mcp.annotation.McpToolParam
import org.springframework.security.core.context.SecurityContextHolder
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken
import org.springframework.stereotype.Component
import java.util.UUID

@Component
class HealthMindMcpTools(
    private val repository: ToolInvocationRepository,
    private val contexts: InternalContextPort,
    private val canonicalJson: CanonicalJson,
    private val schemas: JsonSchemaService,
    private val properties: HealthMindProperties,
    private val captureImages: CaptureImageContentLoader,
) {
    @McpTool(
        name = "nutrimemo.capture_context.get",
        description = "Read confirmed capture images and meal metadata for the current HealthMind task.",
        generateOutputSchema = false,
    )
    fun captureContext(
        @McpToolParam(required = true, description = "HealthMind task UUID") taskId: String,
        @McpToolParam(required = true, description = "HealthMind attempt UUID") attemptId: String,
    ): McpSchema.CallToolResult = invoke(
        "nutrimemo.capture_context.get",
        taskId,
        attemptId,
        contexts::getCaptureContext,
    ) { response ->
        val result = McpSchema.CallToolResult.builder()
            .structuredContent(canonicalJson.toPlainMap(response))
            .isError(false)
        captureImages.load(response).forEach(result::addContent)
        result.build()
    }

    @McpTool(
        name = "orion.nutrition_context.get",
        description = "Read the consent-gated minimal nutrition health context for the current HealthMind task.",
        generateOutputSchema = false,
    )
    fun nutritionContext(
        @McpToolParam(required = true, description = "HealthMind task UUID") taskId: String,
        @McpToolParam(required = true, description = "HealthMind attempt UUID") attemptId: String,
    ): String = invoke(
        "orion.nutrition_context.get",
        taskId,
        attemptId,
        contexts::getNutritionContext,
    ) { canonicalJson.stringify(it) }

    private fun <T> invoke(
        toolCode: String,
        taskId: String,
        attemptId: String,
        call: (ToolInvocationRepository.ToolGrant) -> tools.jackson.databind.JsonNode,
        transform: (tools.jackson.databind.JsonNode) -> T,
    ): T {
        val auth = SecurityContextHolder.getContext().authentication as? JwtAuthenticationToken
            ?: throw IllegalStateException("MCP caller is not authenticated")
        val clientId = auth.token.getClaimAsString("azp") ?: auth.token.getClaimAsString("client_id")
        require(clientId == properties.oauth.allowedDifyClientId) { "MCP caller client is not allowed" }
        val scopes = auth.authorities.mapNotNull { it.authority?.removePrefix("SCOPE_")?.takeIf(String::isNotBlank) }.toSet()
        val callerSubject = auth.token.subject?.let { runCatching { UUID.fromString(it) }.getOrNull() }
        val invocation = repository.authorizeAndStart(toolCode, UUID.fromString(taskId), UUID.fromString(attemptId), callerSubject, scopes)
        return try {
            val request = canonicalJson.parse("""{"attempt_id":"$attemptId","task_id":"$taskId"}""")
            schemas.validate(invocation.grant.requestSchema, request, "TOOL_REQUEST_CONTRACT_INVALID")
            val response = call(invocation.grant)
            schemas.validate(invocation.grant.responseSchema, response, "TOOL_RESPONSE_CONTRACT_INVALID")
            val result = transform(response)
            repository.succeed(invocation, canonicalJson.sha256(response))
            result
        } catch (exception: Exception) {
            val failureCode = if (exception is CaptureImageFetchException) {
                "CAPTURE_IMAGE_FETCH_FAILED"
            } else {
                "DOWNSTREAM_CONTEXT_FAILED"
            }
            repository.fail(invocation, failureCode)
            throw exception
        }
    }
}
