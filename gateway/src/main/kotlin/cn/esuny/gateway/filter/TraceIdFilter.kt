package cn.esuny.gateway.filter

import cn.esuny.gateway.config.FilterOrder
import org.slf4j.MDC
import org.springframework.core.Ordered
import org.springframework.stereotype.Component
import org.springframework.web.server.ServerWebExchange
import org.springframework.web.server.WebFilter
import org.springframework.web.server.WebFilterChain
import reactor.core.publisher.Mono
import java.util.UUID

/**
 * 链路追踪 ID 过滤器 (TraceId Filter)
 *
 * 作用：为每个进入网关的请求生成或提取一个唯一的 Trace ID，
 * 并将其放入 MDC (Mapped Diagnostic Context) 中，以便日志中能包含该 ID。
 * 这样就可以通过同一个 Trace ID 将一个请求在各个微服务中的所有日志串联起来。
 */
@Component
class TraceIdFilter : WebFilter, Ordered {

    companion object {
        const val TRACE_ID_HEADER = "X-Trace-Id"
        const val MDC_TRACE_ID_KEY = "traceId"
    }

    override fun getOrder(): Int = FilterOrder.TRACE_ID // 最高优先级

    override fun filter(exchange: ServerWebExchange, chain: WebFilterChain): Mono<Void> {
        val request = exchange.request
        val response = exchange.response

        // 1. 尝试从请求头中获取已有的 Trace ID
        var traceId = request.headers.getFirst(TRACE_ID_HEADER)

        // 2. 如果请求头中没有，则生成一个新的 UUID 作为 Trace ID
        if (traceId.isNullOrBlank()) {
            traceId = UUID.randomUUID().toString().replace("-", "")
        }

        // 3. 将 Trace ID 放入 MDC
        MDC.put(MDC_TRACE_ID_KEY, traceId)

        // 4. 将 Trace ID 添加到响应头中
        response.headers.set(TRACE_ID_HEADER, traceId)

        // 5. 放行请求
        return chain.filter(exchange).doFinally {
            // 6. 在 finally 块中清除 MDC
            MDC.remove(MDC_TRACE_ID_KEY)
        }
    }
}
