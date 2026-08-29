package cn.esuny.healthmind.infrastructure.config

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.core.convert.converter.Converter
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.core.GrantedAuthority
import org.springframework.security.oauth2.jwt.Jwt
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
                server.jwt { jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter()) }
            }
        return http.build()
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
