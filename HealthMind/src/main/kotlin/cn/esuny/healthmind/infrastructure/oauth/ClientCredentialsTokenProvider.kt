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
        val key = "${config.clientId}|${config.audience}|${config.scope}"
        cache[key]?.takeIf { it.expiresAt.isAfter(Instant.now().plusSeconds(20)) }?.let { return it.value }
        synchronized(cache) {
            cache[key]?.takeIf { it.expiresAt.isAfter(Instant.now().plusSeconds(20)) }?.let { return it.value }
            val form = LinkedMultiValueMap<String, String>().apply {
                add("grant_type", "client_credentials")
                add("client_id", config.clientId)
                add("client_secret", config.clientSecret)
                add("scope", config.scope)
                add("audience", config.audience)
            }
            val response = builder.clone().build().post().uri(config.tokenUri)
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
