package cn.esuny.gateway.config

import org.springframework.context.annotation.Configuration
import org.springframework.web.servlet.config.annotation.CorsRegistry
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer

/**
 * 跨域资源共享（CORS）配置类
 *
 * 注意：此类实现了 WebMvcConfigurer，配置在启动时一次性加载，不支持动态刷新。
 * 因此直接硬编码，不从 application.yaml 或 Nacos 读取。
 * 如果需要变更 CORS 配置，必须重启服务。
 */
@Configuration
class CorsConfig : WebMvcConfigurer {

    /**
     * 配置跨域映射规则
     */
    override fun addCorsMappings(registry: CorsRegistry) {
        registry.addMapping("/**")
            .allowedOriginPatterns("*") // 开发环境允许所有来源，生产环境应限制
            .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
            .allowedHeaders("*")
            .allowCredentials(true)
            .maxAge(3600L) // 预检请求缓存 1 小时
    }
}
