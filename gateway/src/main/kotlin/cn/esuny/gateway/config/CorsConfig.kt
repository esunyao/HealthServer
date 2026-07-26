package cn.esuny.gateway.config

import org.springframework.context.annotation.Configuration
import org.springframework.web.servlet.config.annotation.CorsRegistry
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer

/**
 * 跨域资源共享（CORS）配置类
 *
 * 当浏览器前端运行在 http://localhost:8080，而后端接口在 http://localhost:9000 时，
 * 浏览器的同源策略会阻止前端调用后端。这就需要后端配置 CORS，允许跨域访问。
 * 注意：网关是微服务系统的第一道防线，因此我们把跨域配置统一放在网关上，
 * 后端其他微服务就不需要再配跨域了。
 */
@Configuration
class CorsConfig : WebMvcConfigurer {

    /**
     * 配置跨域映射规则
     */
    override fun addCorsMappings(registry: CorsRegistry) {
        registry.addMapping("/**") // 匹配所有的路径，即所有的请求都应用此跨域规则
            // 允许跨域请求的来源。这里的 "*" 表示允许所有源（开发环境方便）。
            // 警告：在生产环境，强烈建议把 "*" 改为前端应用的实际域名（如 https://www.myapp.com）以保证安全！
            .allowedOriginPatterns("*")
            
            // 允许跨域请求使用的方法。一般只开常用的即可。
            .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
            
            // 允许跨域请求包含哪些自定义的请求头。
            .allowedHeaders("*")
            
            // 是否允许客户端发送凭证（如 Cookie 或者 Authorization 认证头）。
            // 当需要前端带着登录信息跨域时，这里必须设为 true。
            .allowCredentials(true)
            
            // 预检请求（OPTIONS 请求）的缓存时间，单位是秒。
            // 浏览器发送真实跨域请求前会先发一个 OPTIONS 请求试探，
            // 缓存这个试探结果（3600秒 = 1小时），能有效减少网络请求次数，提升性能。
            .maxAge(3600L)
    }
}
