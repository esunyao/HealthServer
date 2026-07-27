package cn.esuny.gateway.config

import org.springframework.beans.factory.annotation.Value
import org.springframework.cloud.context.config.annotation.RefreshScope
import org.springframework.stereotype.Component

/**
 * 限流配置属性类
 *
 * 支持动态刷新：通过 Nacos 修改配置后，无需重启即可生效。
 * 注意：此类必须被 Spring 管理（@Component），且添加 @RefreshScope 注解。
 */
@RefreshScope
@Component
class RateLimitProperties {

    @Value("\${gateway.rate-limit.requests-per-second:20}")
    var requestsPerSecond: Double = 20.0

    @Value("\${gateway.rate-limit.burst-capacity:40}")
    var burstCapacity: Double = 40.0
}