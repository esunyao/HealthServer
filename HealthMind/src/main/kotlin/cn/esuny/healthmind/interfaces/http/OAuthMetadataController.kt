package cn.esuny.healthmind.interfaces.http

import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RestController

@RestController
class OAuthMetadataController(
    private val properties: HealthMindProperties,
) {
    @GetMapping("/.well-known/oauth-protected-resource/mcp")
    fun metadata(): Map<String, Any> = mapOf(
        "resource" to properties.oauth.mcpResourceUri,
        "authorization_servers" to listOf(properties.oauth.issuerUri),
        "bearer_methods_supported" to listOf("header"),
        "scopes_supported" to listOf(
            "healthmind.tool.nutrimemo.capture-context.read",
            "healthmind.tool.orion.nutrition-context.read",
        ),
    )
}
