package cn.esuny.gateway.config

import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.stereotype.Component

/**
 * Authentik OIDC 资源服务器配置。
 *
 * issuerUri 必须与 Authentik OpenID Discovery 文档中的 issuer 字段完全一致，
 * 包括末尾斜杠和端口（若有）。audiences 通常填当前移动端 OIDC Provider 的 Client ID。
 */
@Component
@ConfigurationProperties(prefix = "gateway.authentik")
class AuthentikProperties {
    var issuerUri: String = ""
    var audiences: List<String> = emptyList()

    fun configuredAudiences(): Set<String> = audiences
        .flatMap { it.split(',') }
        .map { it.trim() }
        .filter { it.isNotEmpty() }
        .toSet()
}
