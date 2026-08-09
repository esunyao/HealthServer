package cn.esuny.gateway.filter

import cn.esuny.gateway.config.OidcAuthProperties
import com.fasterxml.jackson.databind.ObjectMapper
import org.junit.jupiter.api.Test
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpMethod
import org.springframework.http.HttpStatus
import org.springframework.mock.http.server.reactive.MockServerHttpRequest
import org.springframework.mock.web.server.MockServerWebExchange
import org.springframework.security.oauth2.jwt.Jwt
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder
import org.springframework.web.server.ServerWebExchange
import org.springframework.web.server.WebFilterChain
import reactor.core.publisher.Mono
import java.time.Instant
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull

class AuthentikAuthFilterTest {

    @Test
    fun `uses verified Authentik subject and removes spoofed identity headers`() {
        val filter = filterWith(ReactiveJwtDecoder { Mono.just(jwt()) })
        val exchange = exchange(
            MockServerHttpRequest.get("/v1/users/me")
                .header(HttpHeaders.AUTHORIZATION, "Bearer access-token")
                .header("X-User-Id", "1")
                .header("X-Auth-Subject", "attacker")
                .header("X-Gateway-Source", "attacker")
                .build()
        )
        var forwarded: ServerWebExchange? = null

        filter.filter(exchange, WebFilterChain { next ->
            forwarded = next
            Mono.empty()
        }).block()

        val headers = requireNotNull(forwarded).request.headers
        assertEquals("d290f1ee-6c54-4b01-90e6-d701748f0851", headers.getFirst("X-Auth-Subject"))
        assertEquals("test", headers.getFirst("X-Auth-Username"))
        assertEquals("test@example.com", headers.getFirst("X-Auth-Email"))
        assertNull(headers.getFirst("X-User-Id"))
        assertNull(headers.getFirst(HttpHeaders.AUTHORIZATION))
        assertNull(headers.getFirst("X-Gateway-Source"))
    }

    @Test
    fun `rejects missing bearer token`() {
        val filter = filterWith(ReactiveJwtDecoder { Mono.just(jwt()) })
        val exchange = exchange(MockServerHttpRequest.get("/v1/users/me").build())

        filter.filter(exchange, WebFilterChain { Mono.empty() }).block()

        assertEquals(HttpStatus.UNAUTHORIZED, exchange.response.statusCode)
    }

    @Test
    fun `rejects invalid token without forwarding request`() {
        val filter = filterWith(ReactiveJwtDecoder { Mono.error(IllegalArgumentException("bad token")) })
        val exchange = exchange(
            MockServerHttpRequest.get("/v1/users/me")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid")
                .build()
        )
        var called = false

        filter.filter(exchange, WebFilterChain {
            called = true
            Mono.empty()
        }).block()

        assertEquals(HttpStatus.UNAUTHORIZED, exchange.response.statusCode)
        assertFalse(called)
    }

    @Test
    fun `whitelist still removes client supplied trusted headers`() {
        val properties = OidcAuthProperties().apply { whitelist = listOf("/actuator/") }
        val filter = AuthentikAuthFilter(
            ReactiveJwtDecoder { Mono.error(AssertionError("decoder must not run")) },
            ObjectMapper(),
            properties
        )
        val exchange = exchange(
            MockServerHttpRequest.method(HttpMethod.OPTIONS, "/actuator/health")
                .header("X-Auth-Subject", "attacker")
                .header(HttpHeaders.AUTHORIZATION, "Bearer ignored")
                .build()
        )
        var forwarded: ServerWebExchange? = null

        filter.filter(exchange, WebFilterChain { next ->
            forwarded = next
            Mono.empty()
        }).block()

        val headers = requireNotNull(forwarded).request.headers
        assertNull(headers.getFirst("X-Auth-Subject"))
        assertNull(headers.getFirst(HttpHeaders.AUTHORIZATION))
    }

    private fun filterWith(decoder: ReactiveJwtDecoder) = AuthentikAuthFilter(
        decoder,
        ObjectMapper(),
        OidcAuthProperties()
    )

    private fun exchange(request: MockServerHttpRequest) = MockServerWebExchange.from(request)

    private fun jwt(): Jwt = Jwt.withTokenValue("access-token")
        .header("alg", "RS256")
        .subject("d290f1ee-6c54-4b01-90e6-d701748f0851")
        .claim("preferred_username", "test")
        .claim("email", "test@example.com")
        .issuedAt(Instant.now())
        .expiresAt(Instant.now().plusSeconds(300))
        .build()
}
