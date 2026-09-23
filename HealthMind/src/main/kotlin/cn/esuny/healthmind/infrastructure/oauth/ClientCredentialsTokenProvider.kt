package cn.esuny.healthmind.infrastructure.oauth

import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.http.MediaType
import org.springframework.stereotype.Component
import org.springframework.util.LinkedMultiValueMap
import org.springframework.web.client.RestClient
import tools.jackson.databind.JsonNode
import java.time.Instant
import java.util.concurrent.ConcurrentHashMap

@Component
class ClientCredentialsTokenProvider(
    @Qualifier("directRestClientBuilder") private val builder: RestClient.Builder,
) {
    private val cache = ConcurrentHashMap<String, CachedToken>()

    fun token(config: HealthMindProperties.OAuth.Client): String {
        return token(config.tokenUri, config.clientId, config.clientSecret, config.audience, config.scope)
    }

    fun token(config: HealthMindProperties.OAuth.Credentials): String =
        token(config.tokenUri, config.clientId, config.clientSecret, config.audience, config.scope)

    private fun token(tokenUri: String, clientId: String, clientSecret: String, audience: String, scope: String): String {
        val key = "$tokenUri|$clientId|$audience|$scope"
        cache[key]?.takeIf { it.expiresAt.isAfter(Instant.now().plusSeconds(20)) }?.let { return it.value }
        synchronized(cache) {
            cache[key]?.takeIf { it.expiresAt.isAfter(Instant.now().plusSeconds(20)) }?.let { return it.value }
            val form = LinkedMultiValueMap<String, String>().apply {
                add("grant_type", "client_credentials")
                add("client_id", clientId)
                add("client_secret", clientSecret)
                add("scope", scope)
            }
            val response = builder.clone().build().post().uri(tokenUri)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(form)
                .retrieve()
                .body(JsonNode::class.java)
                ?: error("OAuth token endpoint returned an empty response")
            val value = response.path("access_token").asString()
            require(value.isNotBlank()) { "OAuth token response did not contain access_token" }
            val cached = CachedToken(value, Instant.now().plusSeconds(response.path("expires_in").asLong(300)))
            cache[key] = cached
            return cached.value
        }
    }

    private data class CachedToken(val value: String, val expiresAt: Instant)
}
