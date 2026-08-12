package cn.esuny.nutrimemo.config

import org.springframework.boot.context.properties.ConfigurationProperties
import java.time.Duration

@ConfigurationProperties("nutri.oss")
data class OssProperties(
    val endpoint: String,
    val presignedAddr: String,
    val accessKey: String,
    val secretKey: String,
    val bucket: String,
    val region: String = "us-east-1",
    val presignedExpiration: Duration = Duration.ofMinutes(5),
    val maxFileSize: Long = 10 * 1024 * 1024,
    val allowedContentTypes: List<String> = listOf("image/jpeg", "image/png", "image/webp")
)
