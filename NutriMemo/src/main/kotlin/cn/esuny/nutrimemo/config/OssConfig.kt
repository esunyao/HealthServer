package cn.esuny.nutrimemo.config

import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider
import software.amazon.awssdk.regions.Region
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.S3Configuration
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import java.net.URI

@Configuration
@EnableConfigurationProperties(OssProperties::class, CaptureProperties::class)
class OssConfig {
    private fun credentials(properties: OssProperties) = StaticCredentialsProvider.create(
        AwsBasicCredentials.create(properties.accessKey, properties.secretKey)
    )

    @Bean
    fun s3Client(properties: OssProperties): S3Client = S3Client.builder()
        .endpointOverride(URI.create(properties.endpoint))
        .credentialsProvider(credentials(properties))
        .region(Region.of(properties.region))
        .forcePathStyle(true)
        .build()

    @Bean
    fun s3Presigner(properties: OssProperties): S3Presigner = S3Presigner.builder()
        .endpointOverride(URI.create(properties.presignedAddr))
        .credentialsProvider(credentials(properties))
        .region(Region.of(properties.region))
        .serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
        .build()
}
