package cn.esuny.gateway.filter

import cn.esuny.gateway.config.FilterOrder
import org.slf4j.LoggerFactory
import org.springframework.core.Ordered
import org.springframework.stereotype.Component
import org.springframework.web.server.ServerWebExchange
import org.springframework.web.server.WebFilter
import org.springframework.web.server.WebFilterChain
import reactor.core.publisher.Mono
import java.net.InetSocketAddress
import java.util.concurrent.TimeUnit

/**
 * 请求日志记录过滤器 (Request Logging Filter)
 *
 * 作用：记录每个 HTTP 请求的基本信息（如 URL、IP 等）以及响应的状态码和耗时。
 * 这对于系统性能监控、故障排查（了解某个请求的耗时和结果）非常关键。
 */
@Component
class RequestLoggingFilter : WebFilter, Ordered {

    private val log = LoggerFactory.getLogger(RequestLoggingFilter::class.java)

    override fun getOrder(): Int = FilterOrder.REQUEST_LOGGING

    override fun filter(exchange: ServerWebExchange, chain: WebFilterChain): Mono<Void> {
        val request = exchange.request
        val response = exchange.response

        val method = request.method.name()
        val uri = request.uri.path
        val clientIp = getClientIp(request)
        val userAgent = request.headers.getFirst("User-Agent") ?: "Unknown"

        log.debug("Request Start: [{}] {} | IP: {} | UA: {}", method, uri, clientIp, userAgent)

        val startTime = System.nanoTime()

        return chain.filter(exchange).doFinally {
            val elapsedNanos = System.nanoTime() - startTime
            val elapsedMillis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos)
            val status = response.statusCode?.value() ?: 0

            log.debug("Request End: [{}] {} | Status: {} | Elapsed: {} ms", method, uri, status, elapsedMillis)
        }
    }

    /**
     * 获取真实的客户端 IP 地址
     */
    private fun getClientIp(request: org.springframework.http.server.reactive.ServerHttpRequest): String {
        val xForwardedFor = request.headers.getFirst("X-Forwarded-For")
        if (!xForwardedFor.isNullOrBlank() && !"unknown".equals(xForwardedFor, ignoreCase = true)) {
            return xForwardedFor.split(",")[0].trim()
        }
        return request.remoteAddress?.address?.hostAddress ?: "unknown"
    }
}
