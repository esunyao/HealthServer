package cn.esuny.gateway.filter

import jakarta.servlet.Filter
import jakarta.servlet.FilterChain
import jakarta.servlet.ServletRequest
import jakarta.servlet.ServletResponse
import jakarta.servlet.http.HttpServletRequest
import jakarta.servlet.http.HttpServletResponse
import org.slf4j.MDC
import org.springframework.core.Ordered
import org.springframework.core.annotation.Order
import org.springframework.stereotype.Component
import java.util.UUID

/**
 * 链路追踪 ID 过滤器 (TraceId Filter)
 * 
 * 作用：为每个进入网关的请求生成或提取一个唯一的 Trace ID，
 * 并将其放入 MDC (Mapped Diagnostic Context) 中，以便日志中能包含该 ID。
 * 这样就可以通过同一个 Trace ID 将一个请求在各个微服务中的所有日志串联起来。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE) // 设置最高优先级，确保请求一进入系统就分配 Trace ID
class TraceIdFilter : Filter {

    companion object {
        const val TRACE_ID_HEADER = "X-Trace-Id"
        const val MDC_TRACE_ID_KEY = "traceId"
    }

    override fun doFilter(request: ServletRequest, response: ServletResponse, chain: FilterChain) {
        val httpRequest = request as HttpServletRequest
        val httpResponse = response as HttpServletResponse

        // 1. 尝试从请求头中获取已有的 Trace ID (可能由上游系统如 Nginx 传递过来)
        var traceId = httpRequest.getHeader(TRACE_ID_HEADER)
        
        // 2. 如果请求头中没有，则生成一个新的 UUID 作为 Trace ID
        if (traceId.isNullOrBlank()) {
            traceId = UUID.randomUUID().toString().replace("-", "")
        }

        try {
            // 3. 将 Trace ID 放入 MDC。SLF4J 会在日志输出时自动提取该变量 (需在 logback.xml 中配置 %X{traceId})
            MDC.put(MDC_TRACE_ID_KEY, traceId)
            
            // 4. 将 Trace ID 也添加到响应头中，方便客户端追踪请求
            httpResponse.setHeader(TRACE_ID_HEADER, traceId)
            
            // 5. 放行请求，继续执行后续的 Filter 和具体的业务逻辑
            chain.doFilter(request, response)
        } finally {
            // 6. 务必在 finally 块中清除 MDC 中的变量！
            // 因为 Servlet 容器使用线程池处理请求，线程会被复用，如果不清除，可能会导致后续请求记录了错误的 Trace ID。
            MDC.remove(MDC_TRACE_ID_KEY)
        }
    }
}
