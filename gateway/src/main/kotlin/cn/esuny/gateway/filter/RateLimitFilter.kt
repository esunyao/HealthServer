package cn.esuny.gateway.filter

import cn.esuny.gateway.model.ApiResponse
import jakarta.servlet.Filter
import jakarta.servlet.FilterChain
import jakarta.servlet.ServletRequest
import jakarta.servlet.ServletResponse
import jakarta.servlet.http.HttpServletRequest
import jakarta.servlet.http.HttpServletResponse
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.core.Ordered
import org.springframework.core.annotation.Order
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import tools.jackson.databind.ObjectMapper
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
@Order(Ordered.HIGHEST_PRECEDENCE + 2) // 在日志过滤器之后执行
class RateLimitFilter(
    private val objectMapper: ObjectMapper,
    @Value("\${gateway.rate-limit.requests-per-second:20}")
    private val requestsPerSecond: Double,
    @Value("\${gateway.rate-limit.burst-capacity:40}")
    private val burstCapacity: Double
) : Filter {

    private val log = LoggerFactory.getLogger(RateLimitFilter::class.java)

    // 使用 ConcurrentHashMap 存储每个 IP 的令牌桶。因为可能并发访问，所以要用线程安全的 Map。
    private val buckets = ConcurrentHashMap<String, TokenBucket>()

    /**
     * 令牌桶数据类
     * @param tokens 当前剩余的令牌数
     * @param lastRefillTime 上次补充令牌的时间戳 (纳秒)
     */
    data class TokenBucket(var tokens: Double, var lastRefillTime: Long)

    override fun doFilter(request: ServletRequest, response: ServletResponse, chain: FilterChain) {
        val httpRequest = request as HttpServletRequest
        val httpResponse = response as HttpServletResponse
        val clientIp = getClientIp(httpRequest)

        // 判断当前请求是否允许通过
        if (allowRequest(clientIp)) {
            chain.doFilter(request, response)
        } else {
            // 如果被限流了，记录日志并返回 429 状态码和 JSON 错误信息
            log.warn("Rate limit exceeded for IP: {}", clientIp)
            httpResponse.status = HttpStatus.TOO_MANY_REQUESTS.value()
            httpResponse.contentType = MediaType.APPLICATION_JSON_VALUE
            httpResponse.characterEncoding = "UTF-8"

            val apiResponse = ApiResponse.error<Nothing>(429, "请求过于频繁，请稍后再试")
            httpResponse.writer.write(objectMapper.writeValueAsString(apiResponse))
        }
    }

    /**
     * 判断是否允许请求通过 (核心限流逻辑)
     */
    private fun allowRequest(clientIp: String): Boolean {
        // computeIfAbsent 会在 Map 中不存在该 IP 时，创建一个新的装满令牌的桶
        val bucket = buckets.computeIfAbsent(clientIp) {
            TokenBucket(burstCapacity, System.nanoTime())
        }

        // 使用 synchronized 锁住当前客户端的桶，保证多线程并发下（同一个 IP 多次并发请求）的数据一致性
        synchronized(bucket) {
            val now = System.nanoTime()
            val timeElapsed = now - bucket.lastRefillTime
            val secondsElapsed = timeElapsed.toDouble() / TimeUnit.SECONDS.toNanos(1)

            // 计算自从上次补充之后，到现在应该补充多少令牌
            val tokensToAdd = secondsElapsed * requestsPerSecond

            // 更新桶内令牌数（不能超过最大容量）和上次补充时间
            if (tokensToAdd > 0) {
                bucket.tokens = min(burstCapacity, bucket.tokens + tokensToAdd)
                bucket.lastRefillTime = now
            }

            // 尝试消费一个令牌
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
    private fun getClientIp(request: HttpServletRequest): String {
        val xForwardedFor = request.getHeader("X-Forwarded-For")
        if (!xForwardedFor.isNullOrBlank() && !"unknown".equals(xForwardedFor, ignoreCase = true)) {
            return xForwardedFor.split(",")[0].trim()
        }
        return request.remoteAddr
    }

    /**
     * 定时清理过期的令牌桶，防止内存泄漏 (Memory Leak)
     * 比如某个 IP 只访问了一次就再也不来了，它的令牌桶就会一直留在内存中。
     * 这里设定每 5 分钟执行一次，清理超过 10 分钟没有活动的桶。
     */
    @Scheduled(fixedRate = 300000) // 每 300,000 毫秒 (5 分钟) 执行一次
    fun cleanupStaleBuckets() {
        val now = System.nanoTime()
        val staleThreshold = TimeUnit.MINUTES.toNanos(10)

        // 遍历并移除过期的桶
        buckets.entries.removeIf { entry ->
            val timeElapsed = now - entry.value.lastRefillTime
            timeElapsed > staleThreshold
        }
        log.debug("Cleaned up stale rate limit buckets. Current active buckets: {}", buckets.size)
    }
}
