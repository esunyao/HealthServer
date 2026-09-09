package cn.esuny.orion.internal.nutrition

import jakarta.validation.constraints.NotBlank
import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator
import org.springframework.security.oauth2.core.OAuth2Error
import org.springframework.security.oauth2.core.OAuth2TokenValidator
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult
import org.springframework.security.oauth2.jwt.Jwt
import org.springframework.security.oauth2.jwt.JwtValidators
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder
import org.springframework.security.web.SecurityFilterChain
import org.springframework.validation.annotation.Validated

@Validated
@ConfigurationProperties("orion.internal.security")
data class OrionInternalSecurityProperties(
    @field:NotBlank val issuerUri: String = "http://localhost:9000/application/o/orion-internal/",
    @field:NotBlank val jwkSetUri: String = "http://localhost:9000/application/o/orion-internal/jwks/",
    @field:NotBlank val audience: String = "orion-internal",
    @field:NotBlank val allowedHealthMindClientId: String = "healthmind-orion",
)

@Configuration
class OrionInternalSecurityConfig(private val properties: OrionInternalSecurityProperties) {
    @Bean
    fun orionSecurityFilterChain(http: HttpSecurity): SecurityFilterChain {
        http.securityMatcher("/internal/**")
            .csrf { it.disable() }
            .authorizeHttpRequests {
                it.anyRequest().hasAuthority("SCOPE_orion.ai-context.read")
            }
            .oauth2ResourceServer { it.jwt { jwt -> jwt.decoder(orionJwtDecoder()) } }
        return http.build()
    }

    @Bean
    fun orionJwtDecoder(): NimbusJwtDecoder {
        val decoder = NimbusJwtDecoder.withJwkSetUri(properties.jwkSetUri).build()
        val issuer = JwtValidators.createDefaultWithIssuer(properties.issuerUri)
        val audience = OAuth2TokenValidator<Jwt> { token ->
            if (token.audience?.contains(properties.audience) == true) OAuth2TokenValidatorResult.success()
            else OAuth2TokenValidatorResult.failure(OAuth2Error("invalid_token", "Required audience is missing", null))
        }
        val caller = OAuth2TokenValidator<Jwt> { token ->
            val clientId = token.getClaimAsString("azp") ?: token.getClaimAsString("client_id")
            if (clientId == properties.allowedHealthMindClientId) OAuth2TokenValidatorResult.success()
            else OAuth2TokenValidatorResult.failure(OAuth2Error("invalid_token", "Caller client is not allowed", null))
        }
        decoder.setJwtValidator(DelegatingOAuth2TokenValidator(issuer, audience, caller))
        return decoder
    }
}
