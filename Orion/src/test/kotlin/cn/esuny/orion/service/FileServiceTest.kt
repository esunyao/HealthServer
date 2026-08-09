package cn.esuny.orion.service

import cn.esuny.orion.config.OssProperties
import cn.esuny.orion.mapper.UserMapper
import cn.esuny.orion.model.dto.file.AvatarPresignRequest
import cn.esuny.orion.service.impl.FileServiceImpl
import io.mockk.every
import io.mockk.mockk
import org.junit.jupiter.api.Test
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import software.amazon.awssdk.services.s3.presigner.model.PresignedPutObjectRequest
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest
import java.net.URL
import java.time.Duration
import java.util.UUID
import kotlin.test.assertTrue

class FileServiceTest {
    @Test
    fun `avatar staging key is namespaced by Authentik UUID`() {
        val presigner = mockk<S3Presigner>()
        val presigned = mockk<PresignedPutObjectRequest>()
        every { presigned.url() } returns URL("https://storage.example/avatar.jpg")
        every { presigner.presignPutObject(any<PutObjectPresignRequest>()) } returns presigned
        val service = FileServiceImpl(
            mockk<S3Client>(), presigner,
            OssProperties(
                endpoint = "https://storage.example", accessKey = "access", secretKey = "secret",
                bucket = "avatars", presignedAddr = "https://storage.example",
                presignedExpiration = Duration.ofMinutes(5), maxFileSize = 1024L,
                allowedContentTypes = listOf("image/jpeg")
            ),
            mockk<UserMapper>(), mockk<FileCleanupTaskService>()
        )
        val userId = UUID.fromString("d290f1ee-6c54-4b01-90e6-d701748f0851")

        val response = service.presignAvatarUpload(userId, AvatarPresignRequest("avatar.jpg", "image/jpeg"))

        assertTrue(response.objectKey.startsWith("avatar-staging/$userId/"))
    }
}
