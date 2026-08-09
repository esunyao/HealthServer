package cn.esuny.gateway.config

import cn.esuny.gateway.security.AudienceValidator
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator
import org.springframework.security.oauth2.core.OAuth2TokenValidator
import org.springframework.security.oauth2.jwt.Jwt
import org.springframework.security.oauth2.jwt.JwtValidators
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders
import reactor.core.publisher.Mono
import reactor.core.scheduler.Schedulers
import java.util.concurrent.atomic.AtomicReference

/**
 * 按 Authentik 的 OpenID Discovery 文档延迟初始化 JWT 解码器。
 *
 * Discovery 需要网络 I/O，因此首次初始化放到 boundedElastic 线程池；初始化成功后复用
 * 解码器及其 JWKS 缓存。若 Authentik 暂时不可用，下一次请求会重试初始化，而非缓存失败结果。
 */
@Configuration
class AuthentikJwtDecoderConfig {

    @Bean
    fun authentikJwtDecoder(properties: AuthentikProperties): ReactiveJwtDecoder =
        LazyAuthentikJwtDecoder(properties)
}

private class LazyAuthentikJwtDecoder(
    private val properties: AuthentikProperties
) : ReactiveJwtDecoder {

    private val initializedDecoder = AtomicReference<ReactiveJwtDecoder>()

    override fun decode(token: String): Mono<Jwt> = decoder()
        .flatMap { it.decode(token) }

    private fun decoder(): Mono<ReactiveJwtDecoder> {
        initializedDecoder.get()?.let { return Mono.just(it) }

        return Mono.fromCallable {
            val created = createDecoder()
            if (initializedDecoder.compareAndSet(null, created)) created else checkNotNull(initializedDecoder.get())
        }.subscribeOn(Schedulers.boundedElastic())
    }

    private fun createDecoder(): ReactiveJwtDecoder {
        val issuerUri = properties.issuerUri.trim()
        require(issuerUri.isNotEmpty()) {
            "AUTHENTIK_ISSUER_URI must be configured with the issuer from Authentik OpenID Discovery."
        }

        val audiences = properties.configuredAudiences()
        require(audiences.isNotEmpty()) {
            "AUTHENTIK_AUDIENCES must include this OIDC application's client ID."
        }

        val decoder = ReactiveJwtDecoders.fromIssuerLocation<NimbusReactiveJwtDecoder>(issuerUri)

        val validators = arrayOf<OAuth2TokenValidator<Jwt>>(
            JwtValidators.createDefaultWithIssuer(issuerUri),
            AudienceValidator(audiences)
        )
        decoder.setJwtValidator(DelegatingOAuth2TokenValidator(*validators))
        return decoder
    }
}
