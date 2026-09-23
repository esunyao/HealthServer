package cn.esuny.healthmind.interfaces.mcp

import cn.esuny.healthmind.application.port.out.InternalContextPort
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.database.ToolInvocationRepository
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import cn.esuny.healthmind.infrastructure.json.JsonSchemaService
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
) {
    @McpTool(
        name = "nutrimemo.capture_context.get",
        description = "Read confirmed capture images and meal metadata for the current HealthMind task.",
        generateOutputSchema = false,
    )
    fun captureContext(
        @McpToolParam(required = true, description = "HealthMind task UUID") taskId: String,
        @McpToolParam(required = true, description = "HealthMind attempt UUID") attemptId: String,
    ): String = invoke("nutrimemo.capture_context.get", taskId, attemptId, contexts::getCaptureContext)

    @McpTool(
        name = "orion.nutrition_context.get",
        description = "Read the consent-gated minimal nutrition health context for the current HealthMind task.",
        generateOutputSchema = false,
    )
    fun nutritionContext(
        @McpToolParam(required = true, description = "HealthMind task UUID") taskId: String,
        @McpToolParam(required = true, description = "HealthMind attempt UUID") attemptId: String,
    ): String = invoke("orion.nutrition_context.get", taskId, attemptId, contexts::getNutritionContext)

    private fun invoke(
        toolCode: String,
        taskId: String,
        attemptId: String,
        call: (ToolInvocationRepository.ToolGrant) -> tools.jackson.databind.JsonNode,
    ): String {
        val auth = SecurityContextHolder.getContext().authentication as? JwtAuthenticationToken
            ?: throw IllegalStateException("MCP caller is not authenticated")
        val clientId = auth.token.getClaimAsString("azp") ?: auth.token.getClaimAsString("client_id")
        require(clientId == properties.oauth.allowedAgentClientId) { "MCP caller client is not allowed" }
        val scopes = auth.authorities.mapNotNull { it.authority?.removePrefix("SCOPE_")?.takeIf(String::isNotBlank) }.toSet()
        val callerSubject = auth.token.subject?.let { runCatching { UUID.fromString(it) }.getOrNull() }
        val invocation = repository.authorizeAndStart(toolCode, UUID.fromString(taskId), UUID.fromString(attemptId), callerSubject, scopes)
        return try {
            val request = canonicalJson.parse("""{"attempt_id":"$attemptId","task_id":"$taskId"}""")
            schemas.validate(invocation.grant.requestSchema, request, "TOOL_REQUEST_CONTRACT_INVALID")
            val response = call(invocation.grant)
            schemas.validate(invocation.grant.responseSchema, response, "TOOL_RESPONSE_CONTRACT_INVALID")
            val json = canonicalJson.stringify(response)
            repository.succeed(invocation, canonicalJson.sha256(response))
            json
        } catch (exception: Exception) {
            repository.fail(invocation, "DOWNSTREAM_CONTEXT_FAILED")
            throw exception
        }
    }
}
