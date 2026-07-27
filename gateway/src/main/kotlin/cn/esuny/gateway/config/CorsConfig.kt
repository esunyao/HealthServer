package cn.esuny.gateway.config

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.web.cors.CorsConfiguration
import org.springframework.web.cors.reactive.CorsWebFilter
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource

/**
 * 跨域资源共享（CORS）配置类
 *
 * 注意：此类配置在启动时一次性加载，不支持动态刷新。
 * 如果需要变更 CORS 配置，必须重启服务。
 */
@Configuration
class CorsConfig {

    /**
     * 配置跨域过滤器
     */
    @Bean
    fun corsWebFilter(): CorsWebFilter {
        val config = CorsConfiguration()
        // 开发环境允许所有来源，生产环境应限制
        config.addAllowedOriginPattern("*")
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

        return CorsWebFilter(source)
    }
}
