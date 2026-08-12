package cn.esuny.gateway.config

import cn.esuny.gateway.security.AudienceValidator
import org.slf4j.LoggerFactory
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

    private val log = LoggerFactory.getLogger(LazyAuthentikJwtDecoder::class.java)

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
        if (issuerUri.isEmpty()) {
            throw IllegalStateException("AUTHENTIK_ISSUER_URI 未配置（空值）：请在 gateway 环境变量/.env 中设置 Authentik issuer，例如 https://auth.lovedage.com:8093/application/o/diet-health/")
        }

        val audiences = properties.configuredAudiences()
        if (audiences.isEmpty()) {
            throw IllegalStateException("AUTHENTIK_AUDIENCES 未配置（空值）：请在 gateway 环境变量/.env 中设置 OIDC client_id")
        }
        log.info("初始化 Authentik JWT 解码器：issuer={} audiences={}", issuerUri, audiences)

        val decoder = ReactiveJwtDecoders.fromIssuerLocation<NimbusReactiveJwtDecoder>(issuerUri)

        val validators = arrayOf<OAuth2TokenValidator<Jwt>>(
            JwtValidators.createDefaultWithIssuer(issuerUri),
            AudienceValidator(audiences)
        )
        decoder.setJwtValidator(DelegatingOAuth2TokenValidator(*validators))
        return decoder
    }
}
