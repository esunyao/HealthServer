package cn.esuny.gateway.config

import org.springframework.cloud.context.config.annotation.RefreshScope
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.core.Ordered
import org.springframework.web.cors.CorsConfiguration
import org.springframework.web.cors.reactive.CorsWebFilter
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource

/**
 * 跨域资源共享（CORS）配置类
 *
 * 配置来源：gateway.cors.allowed-origins（application.yaml / Nacos，支持动态刷新）。
 * 过滤器顺序提到最前（FilterOrder.CORS），确保预检 OPTIONS 最先被处理并短路返回。
 */
@Configuration
class CorsConfig(private val corsProperties: CorsProperties) {

    /**
     * 配置跨域过滤器
     */
    @Bean
    @RefreshScope
    fun corsWebFilter(): CorsWebFilter {
        val config = CorsConfiguration()
        // "*" 走 allowedOriginPattern（允许与 allowCredentials=true 共存）；
        // 具体来源走 addAllowedOrigin（配合 credentials 更安全）。
        if (corsProperties.allowedOrigins.isEmpty() || corsProperties.allowedOrigins.contains("*")) {
            config.addAllowedOriginPattern("*")
        } else {
            corsProperties.allowedOrigins.forEach(config::addAllowedOrigin)
        }
        // 允许的 HTTP 方法
        config.addAllowedMethod("GET")
        config.addAllowedMethod("POST")
        config.addAllowedMethod("PUT")
        config.addAllowedMethod("DELETE")
        config.addAllowedMethod("OPTIONS")
        // 允许的请求头
        config.addAllowedHeader("*")
        // 允许携带凭证
        config.allowCredentials = true
        // 预检请求缓存 1 小时
        config.maxAge = 3600L

        val source = UrlBasedCorsConfigurationSource()
        source.registerCorsConfiguration("/**", config)

        // 关键：Spring 7 的 CorsWebFilter 只实现 WebFilter、不再实现 Ordered（无 getOrder），
        // 默认排在 WebFilter 链最后。混入 Ordered 接口显式指定优先级，确保预检最先被 CORS 处理。
        return object : CorsWebFilter(source), Ordered {
            override fun getOrder(): Int = FilterOrder.CORS
        }
    }
}
