package cn.esuny.gateway.filter

import jakarta.servlet.Filter
import jakarta.servlet.FilterChain
import jakarta.servlet.ServletRequest
import jakarta.servlet.ServletResponse
import jakarta.servlet.http.HttpServletRequest
import jakarta.servlet.http.HttpServletResponse
import org.slf4j.LoggerFactory
import org.springframework.core.Ordered
import org.springframework.core.annotation.Order
import org.springframework.stereotype.Component
import java.util.concurrent.TimeUnit

/**
 * 请求日志记录过滤器 (Request Logging Filter)
 * 
 * 作用：记录每个 HTTP 请求的基本信息（如 URL、IP 等）以及响应的状态码和耗时。
 * 这对于系统性能监控、故障排查（了解某个请求的耗时和结果）非常关键。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1) // 在 TraceIdFilter 之后执行，这样日志里就能带上 Trace ID 了
class RequestLoggingFilter : Filter {

    private val log = LoggerFactory.getLogger(RequestLoggingFilter::class.java)

    override fun doFilter(request: ServletRequest, response: ServletResponse, chain: FilterChain) {
        val httpRequest = request as HttpServletRequest
        val httpResponse = response as HttpServletResponse

        // 获取请求的基本信息
        val method = httpRequest.method
        val uri = httpRequest.requestURI
        val clientIp = getClientIp(httpRequest)
        val userAgent = httpRequest.getHeader("User-Agent") ?: "Unknown"

        // 记录请求开始信息
        log.debug("Request Start: [{}] {} | IP: {} | UA: {}", method, uri, clientIp, userAgent)

        // 记录开始时间。使用 nanoTime 计算时间差比 currentTimeMillis 更精确且不受系统时间修改的影响
        val startTime = System.nanoTime()

        try {
            // 放行，执行后续逻辑
            chain.doFilter(request, response)
        } finally {
            // 计算耗时（毫秒）
            val elapsedNanos = System.nanoTime() - startTime
            val elapsedMillis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos)
            
            val status = httpResponse.status
            
            // 记录请求结束信息，包括状态码和耗时
            log.debug("Request End: [{}] {} | Status: {} | Elapsed: {} ms", method, uri, status, elapsedMillis)
        }
    }

    /**
     * 获取真实的客户端 IP 地址
     * 因为网关往往部署在反向代理（如 Nginx、CDN）之后，直接使用 remoteAddr 可能获取到的是代理服务器的 IP。
     * 所以需要优先检查 X-Forwarded-For 头部。
     */
    private fun getClientIp(request: HttpServletRequest): String {
        val xForwardedFor = request.getHeader("X-Forwarded-For")
        if (!xForwardedFor.isNullOrBlank() && !"unknown".equals(xForwardedFor, ignoreCase = true)) {
            // X-Forwarded-For 可能包含多个 IP，第一个通常是真实的客户端 IP
            return xForwardedFor.split(",")[0].trim()
        }
        return request.remoteAddr
    }
}
