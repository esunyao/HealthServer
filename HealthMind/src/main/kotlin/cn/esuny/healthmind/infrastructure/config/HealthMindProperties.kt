package cn.esuny.healthmind.infrastructure.config

import jakarta.validation.Valid
import jakarta.validation.constraints.Max
import jakarta.validation.constraints.Min
import jakarta.validation.constraints.NotBlank
import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.validation.annotation.Validated
import java.time.Duration

@Validated
@ConfigurationProperties("healthmind")
data class HealthMindProperties(
    @field:Valid val kafka: Kafka = Kafka(),
    @field:Valid val agent: Agent = Agent(),
    @field:Valid val oauth: OAuth = OAuth(),
    @field:Valid val scheduler: Scheduler = Scheduler(),
    @field:Valid val retention: Retention = Retention(),
) {
    data class Kafka(
        @field:NotBlank val captureReadyDestination: String = "nutrition-capture-ready",
        @field:NotBlank val analysisCompletedDestination: String = "nutrition-analysis-completed",
        @field:NotBlank val analysisFailedDestination: String = "nutrition-analysis-failed",
        @field:NotBlank val consumerGroup: String = "healthmind-nutrition-v1",
        val publishTimeout: Duration = Duration.ofSeconds(15),
    )

    data class Agent(
        val deployments: Map<String, String> = emptyMap(),
        @field:Min(1) @field:Max(1000) val maxInFlight: Int = 10,
        val connectTimeout: Duration = Duration.ofSeconds(3),
        val readTimeout: Duration = Duration.ofSeconds(15),
        val pollInterval: Duration = Duration.ofSeconds(5),
    )

    data class OAuth(
        @field:NotBlank val issuerUri: String = "http://localhost:9000/application/o/healthmind-mcp/",
        @field:NotBlank val jwkSetUri: String = "http://localhost:9000/application/o/healthmind-mcp/jwks/",
        @field:NotBlank val expectedMcpAudience: String = "healthmind-mcp",
        @field:NotBlank val allowedAgentClientId: String = "langgraph-healthmind",
        @field:NotBlank val mcpResourceUri: String = "http://localhost:8100/mcp",
        @field:NotBlank val protectedResourceMetadataUri: String = "http://localhost:8100/.well-known/oauth-protected-resource/mcp",
        val connectTimeout: Duration = Duration.ofSeconds(3),
        val readTimeout: Duration = Duration.ofSeconds(15),
        @field:Valid val orion: Client = Client(audience = "orion-internal", scope = "orion.ai-context.read"),
        @field:Valid val nutrimemo: Client = Client(audience = "nutrimemo-internal", scope = "nutrimemo.ai-context.read"),
        @field:Valid val agent: Credentials = Credentials(audience = "healthmind-agent", scope = "healthmind.agent.run"),
    ) {
        data class Credentials(
            @field:NotBlank val tokenUri: String = "http://localhost:9000/application/o/token/",
            @field:NotBlank val clientId: String = "healthmind-agent",
            @field:NotBlank val clientSecret: String = "",
            @field:NotBlank val audience: String,
            @field:NotBlank val scope: String,
        )

        data class Client(
            @field:NotBlank val baseUrl: String = "http://localhost:8090",
            @field:NotBlank val tokenUri: String = "http://localhost:9000/application/o/token/",
            @field:NotBlank val clientId: String = "healthmind-client",
            @field:NotBlank val clientSecret: String = "",
            @field:NotBlank val audience: String,
            @field:NotBlank val scope: String,
        )
    }

    data class Scheduler(
        @field:Min(1) @field:Max(100) val batchSize: Int = 10,
        val taskFixedDelay: Duration = Duration.ofSeconds(1),
        val outboxFixedDelay: Duration = Duration.ofSeconds(1),
        val recoveryFixedDelay: Duration = Duration.ofMinutes(1),
    )

    data class Retention(
        val result: Duration = Duration.ofDays(30),
        val audit: Duration = Duration.ofDays(180),
        val integration: Duration = Duration.ofDays(30),
    )
}
