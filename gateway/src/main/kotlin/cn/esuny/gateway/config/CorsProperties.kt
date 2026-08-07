package cn.esuny.gateway.config

import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.cloud.context.config.annotation.RefreshScope
import org.springframework.stereotype.Component

/**
 * CORS 跨域配置属性。支持 Nacos 动态刷新，修改后无需重启。
 * 配置示例：
 * ```yaml
 * gateway:
 *   cors:
 *     allowed-origins:
 *       - "*"
 * ```
 */
@Component
@RefreshScope
@ConfigurationProperties(prefix = "gateway.cors")
class CorsProperties {
    /** 允许的来源；含 "*" 表示允许所有（生产环境务必改为具体来源） */
    var allowedOrigins: List<String> = mutableListOf("*")
}
