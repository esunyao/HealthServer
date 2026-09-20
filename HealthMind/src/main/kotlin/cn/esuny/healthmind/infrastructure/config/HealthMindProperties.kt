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
    @field:Valid val dify: Dify = Dify(),
    @field:Valid val oauth: OAuth = OAuth(),
    @field:Valid val mcp: Mcp = Mcp(),
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

    data class Dify(
        @field:NotBlank val baseUrl: String = "http://localhost:8080/v1",
        val appKeys: Map<String, String> = emptyMap(),
        val connectTimeout: Duration = Duration.ofSeconds(3),
        val readTimeout: Duration = Duration.ofSeconds(130),
        @field:NotBlank val deploymentVersion: String = "1.17.0",
    )

    data class OAuth(
        @field:NotBlank val issuerUri: String = "http://localhost:9000/application/o/healthmind-mcp/",
        @field:NotBlank val jwkSetUri: String = "http://localhost:9000/application/o/healthmind-mcp/jwks/",
        @field:NotBlank val expectedMcpAudience: String = "healthmind-mcp",
        @field:NotBlank val allowedDifyClientId: String = "dify-healthmind",
        @field:NotBlank val mcpResourceUri: String = "http://localhost:8100/mcp",
        @field:NotBlank val protectedResourceMetadataUri: String = "http://localhost:8100/.well-known/oauth-protected-resource/mcp",
        val connectTimeout: Duration = Duration.ofSeconds(3),
        val readTimeout: Duration = Duration.ofSeconds(15),
        @field:Valid val orion: Client = Client(audience = "orion-internal", scope = "orion.ai-context.read"),
        @field:Valid val nutrimemo: Client = Client(audience = "nutrimemo-internal", scope = "nutrimemo.ai-context.read"),
    ) {
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

    data class Mcp(
        @field:Valid val captureImages: CaptureImages = CaptureImages(),
    ) {
        data class CaptureImages(
            @field:Min(1) @field:Max(100) val maxCount: Int = 10,
            @field:Min(1) val maxImageBytes: Long = 10L * 1024 * 1024,
            @field:Min(1) val maxTotalBytes: Long = 100L * 1024 * 1024,
            val allowedMimeTypes: Set<String> = setOf("image/jpeg", "image/png", "image/webp"),
        )
    }

    data class Retention(
        val result: Duration = Duration.ofDays(30),
        val audit: Duration = Duration.ofDays(180),
        val integration: Duration = Duration.ofDays(30),
    )
}
