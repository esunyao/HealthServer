package cn.esuny.nutrimemo.config

import org.springframework.boot.context.properties.ConfigurationProperties
import java.time.Duration

@ConfigurationProperties("nutri.capture")
data class CaptureProperties(
    val sessionTtl: Duration = Duration.ofHours(24),
    val cleanupInterval: Duration = Duration.ofMinutes(15),
    val maxDraftSessions: Int = 5
)
