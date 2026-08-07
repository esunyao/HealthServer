package cn.esuny.gateway.filter

import cn.esuny.gateway.config.FilterOrder
import cn.esuny.gateway.config.JwtAuthProperties
import cn.esuny.gateway.model.ApiResponse
import cn.esuny.gateway.security.JwtUtil
import com.fasterxml.jackson.databind.ObjectMapper
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.core.Ordered
import org.springframework.data.redis.core.ReactiveRedisTemplate
import org.springframework.http.HttpMethod
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.stereotype.Component
import org.springframework.web.server.ServerWebExchange
import org.springframework.web.server.WebFilter
import org.springframework.web.server.WebFilterChain
import reactor.core.publisher.Mono

/**
 * JWT 认证过滤器
 *
 * 在路由转发前验证 JWT Token，防止客户端伪造 X-User-Id header。
 * 白名单路径（注册、登录、刷新 Token、健康检查）无需认证。
 * 白名单配置在 application.yaml 中，支持 Nacos 动态刷新。
 *
 * 过滤器链顺序：
 * - TraceIdFilter: HIGHEST_PRECEDENCE
 * - RequestLoggingFilter: HIGHEST_PRECEDENCE + 1
 * - RateLimitFilter: HIGHEST_PRECEDENCE + 2
 * - JwtAuthFilter: HIGHEST_PRECEDENCE + 3（本过滤器）
 */
@Component
class JwtAuthFilter(
    private val jwtUtil: JwtUtil,
    private val objectMapper: ObjectMapper,
    // 指定注入名称为 reactiveStringRedisTemplate 的 Bean：
    // 1. 消除依赖注入歧义（防止与默认的 reactiveRedisTemplate<Object, Object> 冲突导致启动报错）
    // 2. 保证 Redis 的 Key/Value 均使用 UTF-8 字符串格式序列化，避免查询黑名单时出现乱码匹配失败
    @Qualifier("reactiveStringRedisTemplate")
    private val redisTemplate: ReactiveRedisTemplate<String, String>,
    private val jwtAuthProperties: JwtAuthProperties
) : WebFilter, Ordered {

    private val log = LoggerFactory.getLogger(JwtAuthFilter::class.java)

    companion object {
        // Redis 黑名单 key 前缀（与 Orion 保持一致）
        private const val BLACKLIST_PREFIX = "token_blacklist:"
    }

    override fun getOrder(): Int = FilterOrder.JWT_AUTH

    override fun filter(exchange: ServerWebExchange, chain: WebFilterChain): Mono<Void> {
        val path = exchange.request.path.value()

        // 0. 预检请求放行：浏览器 CORS 预检不带 token，且不含任何业务操作
        if (exchange.request.method == HttpMethod.OPTIONS) {
            log.debug("Preflight request, skipping auth: {}", path)
            return chain.filter(exchange)
        }

        // 1. 白名单检查
        if (isWhitelistPath(path)) {
            log.debug("Whitelist path, skipping auth: {}", path)
            return chain.filter(exchange)
        }

        // 2. 提取 Token
        val token = extractToken(exchange.request)
        if (token == null) {
            log.warn("Missing authorization token for path: {}", path)
            return unauthorized(exchange, "缺少认证 Token")
        }

        // 3. 验证 Token
        if (!jwtUtil.validateAccessToken(token)) {
            log.warn("Invalid or expired token for path: {}", path)
            return unauthorized(exchange, "Token 无效或已过期")
        }

        // 4. 检查 Token 黑名单（已登出的 Token）
        return checkBlacklist(token)
            .flatMap { isBlacklisted ->
                if (isBlacklisted) {
                    log.warn("Token is blacklisted (logged out): {}", path)
                    unauthorized(exchange, "Token 已失效，请重新登录")
                } else {
                    // 5. 提取 userId 并注入 Header
                    val userId = jwtUtil.getUserId(token)
                    log.debug("Authenticated user: {} for path: {}", userId, path)

                    val mutatedRequest = exchange.request.mutate()
                        .header("X-User-Id", userId)
                        .build()

                    chain.filter(exchange.mutate().request(mutatedRequest).build())
                }
            }
    }

    /**
     * 检查 Token 是否在黑名单中
     */
    private fun checkBlacklist(token: String): Mono<Boolean> {
        val key = BLACKLIST_PREFIX + token
        return redisTemplate.hasKey(key)
    }

    /**
     * 判断是否为白名单路径
     * 白名单配置支持 Nacos 动态刷新
     */
    private fun isWhitelistPath(path: String): Boolean {
        return jwtAuthProperties.whitelist.any { path.startsWith(it) }
    }

    /**
     * 从请求头中提取 Bearer Token
     */
    private fun extractToken(request: org.springframework.http.server.reactive.ServerHttpRequest): String? {
        val authHeader = request.headers.getFirst("Authorization")
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            return authHeader.substring(7).trim()
        }
        return null
    }

    /**
     * 返回 401 未授权响应
     */
    private fun unauthorized(exchange: ServerWebExchange, message: String): Mono<Void> {
        val response = exchange.response
        response.statusCode = HttpStatus.UNAUTHORIZED
        response.headers.contentType = MediaType.APPLICATION_JSON

        val apiResponse = ApiResponse.error<Nothing>(401, message)
        val json = objectMapper.writeValueAsString(apiResponse)
        val buffer = response.bufferFactory().wrap(json.toByteArray(Charsets.UTF_8))

        return response.writeWith(Mono.just(buffer)).then()
    }
}
