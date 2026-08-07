package cn.esuny.gateway.config

import org.springframework.core.Ordered

/**
 * 网关过滤器执行顺序统一管理。
 * 数值越小优先级越高、越先执行。
 * 新增过滤器时必须在此登记，禁止在各过滤器类里散落魔法数。
 */
object FilterOrder {
    const val CORS            = Ordered.HIGHEST_PRECEDENCE        // 跨域最先，预检在此短路返回
    const val TRACE_ID        = Ordered.HIGHEST_PRECEDENCE + 1
    const val REQUEST_LOGGING = Ordered.HIGHEST_PRECEDENCE + 2
    const val RATE_LIMIT      = Ordered.HIGHEST_PRECEDENCE + 3
    const val JWT_AUTH        = Ordered.HIGHEST_PRECEDENCE + 4
}
