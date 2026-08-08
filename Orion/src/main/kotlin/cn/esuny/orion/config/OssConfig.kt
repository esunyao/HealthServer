package cn.esuny.orion.config

import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider
import software.amazon.awssdk.regions.Region
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import java.net.URI

/**
 * OSS 对象存储配置类
 *
 * 初始化 S3 客户端 (S3Client) 和预签名器 (S3Presigner)，支持 S3 兼容协议（RustFS / MinIO / 阿里云 OSS / 腾讯云 COS 等）
 */
@Configuration
@EnableConfigurationProperties(OssProperties::class)
class OssConfig {

    /**
     * 初始化同步 S3 客户端 Bean
     *
     * 用于后端服务端直接与 OSS 进行交互，执行文件上传、下载、删除、存储桶管理等标准 API 操作。
     *
     * @param properties OSS 配置属性，自动从 application.yml 中绑定注入
     * @return 配置完成的 S3Client 实例
     */
    @Bean
    fun s3Client(properties: OssProperties): S3Client {
        // 创建 AK/SK 静态凭证提供者
        val credentials = AwsBasicCredentials.create(properties.accessKey, properties.secretKey)
        val credentialsProvider = StaticCredentialsProvider.create(credentials)

        return S3Client.builder()
            // 覆盖默认的 AWS S3 服务 Endpoint 地址，使其指向私有部署或第三方 S3 兼容服务
            .endpointOverride(URI.create(properties.endpoint))
            .credentialsProvider(credentialsProvider)
            .region(Region.of(properties.region))
            // 强制启用路径样式 (Path-Style: http://endpoint/bucket/object)，自建 S3 (如 RustFS / MinIO) 无泛域名解析时必须开启
            .forcePathStyle(true)
            .build()
    }

    /**
     * 初始化 S3 预签名器 Bean
     *
     * 用于生成带有安全签名的临时访问 URL（Presigned URL），例如前端直传文件、限制有效期的临时文件下载/预览链接。
     *
     * @param properties OSS 配置属性
     * @return 配置完成的 S3Presigner 实例
     */
    @Bean
    fun s3Presigner(properties: OssProperties): S3Presigner {
        // 创建 AK/SK 静态凭证提供者
        val credentials = AwsBasicCredentials.create(properties.accessKey, properties.secretKey)
        val credentialsProvider = StaticCredentialsProvider.create(credentials)

        return S3Presigner.builder()
            // 覆盖默认 Endpoint 地址
            .endpointOverride(URI.create(properties.presignedAddr))
            .credentialsProvider(credentialsProvider)
            .region(Region.of(properties.region))
            .build()
    }
}
