package cn.esuny.healthmind.interfaces.http

import org.springframework.beans.factory.annotation.Value
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RestController

@RestController
class OAuthMetadataController(
    @Value("\${spring.security.oauth2.resourceserver.jwt.issuer-uri}") private val issuer: String,
) {
    @GetMapping("/.well-known/oauth-protected-resource/mcp")
    fun metadata(): Map<String, Any> = mapOf(
        "resource" to "/mcp",
        "authorization_servers" to listOf(issuer),
        "bearer_methods_supported" to listOf("header"),
    )
}
