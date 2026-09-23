package cn.esuny.healthmind.infrastructure.config

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatus
import org.springframework.core.convert.converter.Converter
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.core.GrantedAuthority
import org.springframework.security.oauth2.jwt.Jwt
import org.springframework.security.oauth2.jwt.JwtValidators
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator
import org.springframework.security.oauth2.core.OAuth2Error
import org.springframework.security.oauth2.core.OAuth2TokenValidator
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter
import org.springframework.security.web.SecurityFilterChain

@Configuration
class SecurityConfig(private val properties: HealthMindProperties) {
    @Bean
    fun securityFilterChain(http: HttpSecurity): SecurityFilterChain {
        http
            .csrf { it.ignoringRequestMatchers("/mcp/**") }
            .authorizeHttpRequests {
                it.requestMatchers("/actuator/health", "/.well-known/oauth-protected-resource/**").permitAll()
                    .requestMatchers("/mcp/**").authenticated()
                    .anyRequest().denyAll()
            }
            .oauth2ResourceServer { server ->
                server.protectedResourceMetadata { metadata ->
                    metadata.protectedResourceMetadataCustomizer { builder ->
                        builder.resource(properties.oauth.mcpResourceUri)
                            .authorizationServer(properties.oauth.issuerUri)
                            .scope("healthmind.tool.nutrimemo.capture-context.read")
                            .scope("healthmind.tool.orion.nutrition-context.read")
                            .tlsClientCertificateBoundAccessTokens(false)
                    }
                }
                server.authenticationEntryPoint { _, response, exception ->
                    val error = (exception as? org.springframework.security.oauth2.core.OAuth2AuthenticationException)
                        ?.error?.errorCode
                    val challenge = buildString {
                        append("Bearer resource_metadata=\"")
                        append(properties.oauth.protectedResourceMetadataUri)
                        append('"')
                        if (!error.isNullOrBlank()) append(", error=\"").append(error).append('"')
                    }
                    response.status = HttpStatus.UNAUTHORIZED.value()
                    response.setHeader(HttpHeaders.WWW_AUTHENTICATE, challenge)
                }
                server.jwt { jwt ->
                    jwt.decoder(healthMindJwtDecoder())
                    jwt.jwtAuthenticationConverter(jwtAuthenticationConverter())
                }
            }
        return http.build()
    }

    @Bean
    fun healthMindJwtDecoder(): NimbusJwtDecoder {
        val decoder = NimbusJwtDecoder.withJwkSetUri(properties.oauth.jwkSetUri).build()
        val audience = OAuth2TokenValidator<Jwt> { token ->
            if (token.audience?.contains(properties.oauth.expectedMcpAudience) == true) OAuth2TokenValidatorResult.success()
            else OAuth2TokenValidatorResult.failure(OAuth2Error("invalid_token", "Required audience is missing", null))
        }
        val caller = OAuth2TokenValidator<Jwt> { token ->
            val clientId = token.getClaimAsString("azp") ?: token.getClaimAsString("client_id")
            if (clientId == properties.oauth.allowedAgentClientId) OAuth2TokenValidatorResult.success()
            else OAuth2TokenValidatorResult.failure(OAuth2Error("invalid_token", "Caller client is not allowed", null))
        }
        decoder.setJwtValidator(DelegatingOAuth2TokenValidator(JwtValidators.createDefaultWithIssuer(properties.oauth.issuerUri), audience, caller))
        return decoder
    }

    @Bean
    fun jwtAuthenticationConverter(): JwtAuthenticationConverter {
        val scopes = JwtGrantedAuthoritiesConverter()
        val converter = JwtAuthenticationConverter()
        converter.setJwtGrantedAuthoritiesConverter(Converter<Jwt, Collection<GrantedAuthority>> { jwt ->
            val audience = jwt.audience ?: emptyList()
            if (!audience.contains(properties.oauth.expectedMcpAudience)) emptyList() else scopes.convert(jwt)
        })
        return converter
    }
}
