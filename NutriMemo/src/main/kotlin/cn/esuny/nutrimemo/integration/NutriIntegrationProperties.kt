package cn.esuny.nutrimemo.integration

import jakarta.validation.constraints.NotBlank
import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.validation.annotation.Validated
import java.time.Duration

@Validated
@ConfigurationProperties("nutri.integration")
data class NutriIntegrationProperties(
    @field:NotBlank val captureReadyDestination: String = "nutrition-capture-ready",
    @field:NotBlank val analysisCompletedDestination: String = "nutrition-analysis-completed",
    @field:NotBlank val analysisFailedDestination: String = "nutrition-analysis-failed",
    @field:NotBlank val consumerGroup: String = "nutrimemo-analysis-result-v1",
    val outboxFixedDelay: Duration = Duration.ofSeconds(1),
    val recoveryFixedDelay: Duration = Duration.ofMinutes(1),
    val publishTimeout: Duration = Duration.ofSeconds(15),
)
