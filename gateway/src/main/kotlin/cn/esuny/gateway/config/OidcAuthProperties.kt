package cn.esuny.gateway.config

import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.cloud.context.config.annotation.RefreshScope
import org.springframework.stereotype.Component

/**
 * OIDC 认证白名单配置属性。
 *
 * 支持 Nacos 动态刷新，修改配置后无需重启 Gateway。
 *
 * 配置示例：
 * ```yaml
 * gateway:
 *   oidc-auth:
 *     whitelist:
 *       - /v1/auth/
 *       - /actuator/
 *       - /fallback
 * ```
 */
@Component
@RefreshScope
@ConfigurationProperties(prefix = "gateway.oidc-auth")
class OidcAuthProperties {
    /** 白名单路径前缀列表，匹配的路径无需 OIDC Access Token */
    var whitelist: List<String> = mutableListOf()
}
