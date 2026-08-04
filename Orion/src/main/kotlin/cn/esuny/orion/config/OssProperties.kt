package cn.esuny.orion.config

import org.springframework.boot.context.properties.ConfigurationProperties
import java.time.Duration

/**
 * OSS 对象存储配置属性
 *
 * 支持 S3 兼容协议（RustFS / MinIO / 阿里云 OSS）
 */
@ConfigurationProperties(prefix = "oss")
data class OssProperties(
    /** 对象存储端点 */
    val endpoint: String,
    /** 访问密钥 */
    val accessKey: String,
    /** 私密密钥 */
    val secretKey: String,
    /** 存储桶名称 */
    val bucket: String,
    /** 区域（RustFS 默认 us-east-1） */
    val region: String = "us-east-1",
    /** 预签名 URL 有效期 */
    val presignedExpiration: Duration = Duration.ofMinutes(5),
    /** 最大文件大小（字节） */
    val maxFileSize: Long = 5 * 1024 * 1024,  // 5MB
    /** 允许的 Content-Type */
    val allowedContentTypes: List<String> = listOf(
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif"
    ),
    /** CDN 域名（可选，用于生成访问 URL） */
    val cdnDomain: String? = null,
    /** 对象清理任务配置 */
    val cleanup: CleanupProperties = CleanupProperties()
)

data class CleanupProperties(
    /** 清理任务调度间隔 */
    val fixedDelay: Long = 60_000,
    /** 单次领取的清理任务数量 */
    val batchSize: Int = 100,
    /** 正式区孤儿对象对账表达式 */
    val orphanScanCron: String = "0 30 3 * * *"
)
