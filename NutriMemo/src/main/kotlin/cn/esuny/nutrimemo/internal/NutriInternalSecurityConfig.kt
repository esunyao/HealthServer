package cn.esuny.nutrimemo.internal

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
@ConfigurationProperties("nutri.internal.security")
data class NutriInternalSecurityProperties(
    @field:NotBlank val issuerUri: String = "http://localhost:9000/application/o/nutrimemo-internal/",
    @field:NotBlank val jwkSetUri: String = "http://localhost:9000/application/o/nutrimemo-internal/jwks/",
    @field:NotBlank val audience: String = "nutrimemo-internal",
    @field:NotBlank val allowedHealthMindClientId: String = "healthmind-nutrimemo",
)

@Configuration
class NutriInternalSecurityConfig(private val properties: NutriInternalSecurityProperties) {
    @Bean
    fun nutriSecurityFilterChain(http: HttpSecurity): SecurityFilterChain {
        http.securityMatcher("/internal/**")
            .csrf { it.disable() }
            .authorizeHttpRequests {
                it.anyRequest().hasAuthority("SCOPE_nutrimemo.ai-context.read")
            }
            .oauth2ResourceServer { it.jwt { jwt -> jwt.decoder(nutriJwtDecoder()) } }
        return http.build()
    }

    @Bean
    fun nutriJwtDecoder(): NimbusJwtDecoder {
        val decoder = NimbusJwtDecoder.withJwkSetUri(properties.jwkSetUri).build()
        val audience = OAuth2TokenValidator<Jwt> { token ->
            if (token.audience?.contains(properties.audience) == true) OAuth2TokenValidatorResult.success()
            else OAuth2TokenValidatorResult.failure(OAuth2Error("invalid_token", "Required audience is missing", null))
        }
        val caller = OAuth2TokenValidator<Jwt> { token ->
            val clientId = token.getClaimAsString("azp") ?: token.getClaimAsString("client_id")
            if (clientId == properties.allowedHealthMindClientId) OAuth2TokenValidatorResult.success()
            else OAuth2TokenValidatorResult.failure(OAuth2Error("invalid_token", "Caller client is not allowed", null))
        }
        decoder.setJwtValidator(DelegatingOAuth2TokenValidator(JwtValidators.createDefaultWithIssuer(properties.issuerUri), audience, caller))
        return decoder
    }
}
