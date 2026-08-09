package cn.esuny.gateway.filter

import cn.esuny.gateway.config.FilterOrder
import cn.esuny.gateway.config.OidcAuthProperties
import cn.esuny.gateway.model.ApiResponse
import com.fasterxml.jackson.databind.ObjectMapper
import org.slf4j.LoggerFactory
import org.springframework.core.Ordered
import org.springframework.http.HttpMethod
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.http.server.reactive.ServerHttpRequest
import org.springframework.security.oauth2.jwt.Jwt
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder
import org.springframework.stereotype.Component
import org.springframework.web.server.ServerWebExchange
import org.springframework.web.server.WebFilter
import org.springframework.web.server.WebFilterChain
import reactor.core.publisher.Mono
import java.util.UUID

/**
 * Authentik OIDC Access Token 认证过滤器。
 *
 * 网关通过 Authentik Discovery/JWKS 验证签名、issuer、时效和 audience。下游服务不再
 * 接收客户端提供的身份头或原始 Access Token，只接收本过滤器在验签成功后写入的
 * X-Auth-Subject（Authentik 用户 UUID）。
 */
@Component
class AuthentikAuthFilter(
    private val jwtDecoder: ReactiveJwtDecoder,
    private val objectMapper: ObjectMapper,
    private val oidcAuthProperties: OidcAuthProperties
) : WebFilter, Ordered {

    private val log = LoggerFactory.getLogger(AuthentikAuthFilter::class.java)

    override fun getOrder(): Int = FilterOrder.AUTHENTIK_AUTH

    override fun filter(exchange: ServerWebExchange, chain: WebFilterChain): Mono<Void> {
        val path = exchange.request.path.value()
        val sanitizedRequest = sanitizeRequest(exchange.request)
        val sanitizedExchange = exchange.mutate().request(sanitizedRequest).build()

        if (exchange.request.method == HttpMethod.OPTIONS || isWhitelistPath(path)) {
            return chain.filter(sanitizedExchange)
        }

        val token = extractBearerToken(exchange.request)
            ?: return unauthorized(exchange, "缺少认证 Token")

        return jwtDecoder.decode(token)
            .flatMap { jwt ->
                val subject = jwt.uuidSubjectOrNull()
                    ?: return@flatMap unauthorized(exchange, "认证主体无效")

                val authenticatedRequest = sanitizedRequest.mutate()
                    .headers { headers ->
                        headers.set(HEADER_AUTH_SUBJECT, subject)
                        jwt.stringClaim("preferred_username")?.let {
                            headers.set(HEADER_AUTH_USERNAME, it)
                        }
                        jwt.stringClaim("email")?.let {
                            headers.set(HEADER_AUTH_EMAIL, it)
                        }
                        jwt.stringClaim("name")?.let {
                            headers.set(HEADER_AUTH_DISPLAY_NAME, it)
                        }
                        headers.set(HEADER_AUTH_EMAIL_VERIFIED, jwt.booleanClaim("email_verified").toString())
                    }
                    .build()

                chain.filter(sanitizedExchange.mutate().request(authenticatedRequest).build())
            }
            .onErrorResume { error ->
                log.warn("Authentik token rejected for path {}: {}", path, error.javaClass.simpleName)
                unauthorized(exchange, "Token 无效或已过期")
            }
    }

    private fun isWhitelistPath(path: String): Boolean =
        oidcAuthProperties.whitelist.any(path::startsWith)

    private fun extractBearerToken(request: ServerHttpRequest): String? {
        val header = request.headers.getFirst("Authorization") ?: return null
        if (!header.startsWith("Bearer ", ignoreCase = true)) return null

        return header.substringAfter(' ').trim().takeIf(String::isNotEmpty)
    }

    /** 清理所有只能由网关注入的请求头，防止客户端伪造内部身份或网关来源。 */
    private fun sanitizeRequest(request: ServerHttpRequest): ServerHttpRequest = request.mutate()
        .headers { headers -> TRUSTED_HEADERS.forEach(headers::remove) }
        .build()

    private fun Jwt.uuidSubjectOrNull(): String? = runCatching {
        UUID.fromString(subject).toString()
    }.getOrNull()

    private fun Jwt.stringClaim(name: String): String? = (claims[name] as? String)
        ?.trim()
        ?.takeIf(String::isNotEmpty)

    private fun Jwt.booleanClaim(name: String): Boolean = when (val value = claims[name]) {
        is Boolean -> value
        is String -> value.equals("true", ignoreCase = true)
        else -> false
    }

    private fun unauthorized(exchange: ServerWebExchange, message: String): Mono<Void> {
        val response = exchange.response
        response.statusCode = HttpStatus.UNAUTHORIZED
        response.headers.contentType = MediaType.APPLICATION_JSON

        val body = objectMapper.writeValueAsBytes(ApiResponse.error<Nothing>(401, message))
        return response.writeWith(Mono.just(response.bufferFactory().wrap(body))).then()
    }

    private companion object {
        const val HEADER_AUTH_SUBJECT = "X-Auth-Subject"
        const val HEADER_AUTH_USERNAME = "X-Auth-Username"
        const val HEADER_AUTH_EMAIL = "X-Auth-Email"
        const val HEADER_AUTH_DISPLAY_NAME = "X-Auth-Display-Name"
        const val HEADER_AUTH_EMAIL_VERIFIED = "X-Auth-Email-Verified"

        val TRUSTED_HEADERS = setOf(
            "Authorization",
            "X-User-Id",
            HEADER_AUTH_SUBJECT,
            HEADER_AUTH_USERNAME,
            HEADER_AUTH_EMAIL,
            HEADER_AUTH_DISPLAY_NAME,
            HEADER_AUTH_EMAIL_VERIFIED,
            "X-Gateway-Source"
        )
    }
}
