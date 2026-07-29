package cn.esuny.gateway.config

import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.stereotype.Component

/**
 * JWT 配置属性
 *
 * 从 application.yaml 中的 jwt.* 配置绑定。
 * Gateway 只需要验证 Token，不需要签发，所以不需要 expiration 配置。
 */
@Component
@ConfigurationProperties(prefix = "jwt")
class JwtProperties {
    lateinit var secret: String
}
