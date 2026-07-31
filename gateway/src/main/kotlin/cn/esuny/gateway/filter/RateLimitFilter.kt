package cn.esuny.gateway.filter

import cn.esuny.gateway.config.RateLimitProperties
import cn.esuny.gateway.model.ApiResponse
import com.fasterxml.jackson.databind.ObjectMapper
import org.slf4j.LoggerFactory
import org.springframework.core.Ordered
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.web.server.ServerWebExchange
import org.springframework.web.server.WebFilter
import org.springframework.web.server.WebFilterChain
import reactor.core.publisher.Mono
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import kotlin.math.min

/**
 * 令牌桶速率限制过滤器 (Rate Limit Filter)
 *
 * 作用：基于客户端 IP 进行限流，防止恶意请求或瞬时高并发导致系统崩溃。
 * 使用了简单的内存令牌桶算法 (Token Bucket)：
 * - 系统以恒定速率向桶里放入令牌 (requests-per-second)。
 * - 桶的容量是固定的 (burst-capacity)。
 * - 每次请求消耗一个令牌，如果桶空了，就拒绝请求 (429 Too Many Requests)。
 */
@Component
class RateLimitFilter(
    private val objectMapper: ObjectMapper,
    private val rateLimitProperties: RateLimitProperties
) : WebFilter, Ordered {

    private val log = LoggerFactory.getLogger(RateLimitFilter::class.java)

    // 使用 ConcurrentHashMap 存储每个 IP 的令牌桶
    private val buckets = ConcurrentHashMap<String, TokenBucket>()

    data class TokenBucket(var tokens: Double, var lastRefillTime: Long)

    override fun getOrder(): Int = Ordered.HIGHEST_PRECEDENCE + 2 // 在日志过滤器之后执行

    override fun filter(exchange: ServerWebExchange, chain: WebFilterChain): Mono<Void> {
        val clientIp = getClientIp(exchange)

        return if (allowRequest(clientIp)) {
            chain.filter(exchange)
        } else {
            log.warn("Rate limit exceeded for IP: {}", clientIp)
            val response = exchange.response
            response.statusCode = HttpStatus.TOO_MANY_REQUESTS
            response.headers.contentType = MediaType.APPLICATION_JSON
            response.headers.set("Content-Type", MediaType.APPLICATION_JSON_VALUE + ";charset=UTF-8")

            val apiResponse = ApiResponse.error<Nothing>(429, "请求过于频繁，请稍后再试")
            val json = objectMapper.writeValueAsString(apiResponse)
            val buffer = response.bufferFactory().wrap(json.toByteArray(Charsets.UTF_8))

            response.writeWith(Mono.just(buffer)).then()
        }
    }

    /**
     * 判断是否允许请求通过 (核心限流逻辑)
     */
    private fun allowRequest(clientIp: String): Boolean {
        val bucket = buckets.computeIfAbsent(clientIp) {
            TokenBucket(rateLimitProperties.burstCapacity, System.nanoTime())
        }

        synchronized(bucket) {
            val now = System.nanoTime()
            val timeElapsed = now - bucket.lastRefillTime
            val secondsElapsed = timeElapsed.toDouble() / TimeUnit.SECONDS.toNanos(1)

            val tokensToAdd = secondsElapsed * rateLimitProperties.requestsPerSecond

            if (tokensToAdd > 0) {
                bucket.tokens = min(rateLimitProperties.burstCapacity, bucket.tokens + tokensToAdd)
                bucket.lastRefillTime = now
            }

            return if (bucket.tokens >= 1.0) {
                bucket.tokens -= 1.0
                true
            } else {
                false
            }
        }
    }

    /**
     * 获取客户端 IP
     */
    private fun getClientIp(exchange: ServerWebExchange): String {
        val request = exchange.request
        val xForwardedFor = request.headers.getFirst("X-Forwarded-For")
        if (!xForwardedFor.isNullOrBlank() && !"unknown".equals(xForwardedFor, ignoreCase = true)) {
            return xForwardedFor.split(",")[0].trim()
        }
        return request.remoteAddress?.address?.hostAddress ?: "unknown"
    }

    /**
     * 定时清理过期的令牌桶，防止内存泄漏
     */
    @Scheduled(fixedRate = 300000)
    fun cleanupStaleBuckets() {
        val now = System.nanoTime()
        val staleThreshold = TimeUnit.MINUTES.toNanos(10)

        buckets.entries.removeIf { entry ->
            val timeElapsed = now - entry.value.lastRefillTime
            timeElapsed > staleThreshold
        }
        log.debug("Cleaned up stale rate limit buckets. Current active buckets: {}", buckets.size)
    }
}
