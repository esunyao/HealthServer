package cn.esuny.healthmind.infrastructure.config

import org.junit.jupiter.api.Test
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.context.annotation.Import
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity
import org.springframework.security.web.FilterChainProxy
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.*
import org.springframework.test.web.servlet.setup.MockMvcBuilders
import org.springframework.web.context.WebApplicationContext
import org.springframework.web.servlet.config.annotation.EnableWebMvc

@SpringJUnitWebConfig(OAuthMetadataSecurityTest.Config::class)
class OAuthMetadataSecurityTest {
    @Autowired
    lateinit var context: WebApplicationContext

    @Autowired
    lateinit var filters: FilterChainProxy

    @Test
    fun `security filter publishes authentik discovery metadata without client certificate binding`() {
        val builder = MockMvcBuilders.webAppContextSetup(context)
        builder.addFilters<org.springframework.test.web.servlet.setup.DefaultMockMvcBuilder>(filters)
        val mvc = builder.build()
        mvc.perform(get("/.well-known/oauth-protected-resource/mcp"))
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.resource").value("https://healthmind.example/mcp"))
            .andExpect(jsonPath("$.authorization_servers[0]").value("https://auth.example/application/o/healthmind-mcp/"))
            .andExpect(jsonPath("$.scopes_supported.length()").value(2))
            .andExpect(jsonPath("$.scopes_supported[0]").value("healthmind.tool.nutrimemo.capture-context.read"))
            .andExpect(jsonPath("$.scopes_supported[1]").value("healthmind.tool.orion.nutrition-context.read"))
            .andExpect(jsonPath("$.bearer_methods_supported[0]").value("header"))
            .andExpect(jsonPath("$.tls_client_certificate_bound_access_tokens").value(false))
        mvc.perform(post("/mcp").contentType("application/json").content("{}"))
            .andExpect(status().isUnauthorized)
            .andExpect(header().string("WWW-Authenticate", "Bearer resource_metadata=\"https://healthmind.example/.well-known/oauth-protected-resource/mcp\""))
    }

    @Configuration(proxyBeanMethods = false)
    @EnableWebSecurity
    @EnableWebMvc
    @Import(SecurityConfig::class)
    class Config {
        @Bean
        fun properties() = HealthMindProperties(oauth = HealthMindProperties.OAuth(
            issuerUri = "https://auth.example/application/o/healthmind-mcp/",
            jwkSetUri = "https://auth.example/application/o/healthmind-mcp/jwks/",
            mcpResourceUri = "https://healthmind.example/mcp",
            protectedResourceMetadataUri = "https://healthmind.example/.well-known/oauth-protected-resource/mcp",
        ))
    }
}
