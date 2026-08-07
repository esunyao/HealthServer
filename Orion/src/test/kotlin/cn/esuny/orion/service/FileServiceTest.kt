package cn.esuny.orion.service

import cn.esuny.orion.config.OssProperties
import cn.esuny.orion.handler.BusinessException
import cn.esuny.orion.mapper.UserMapper
import cn.esuny.orion.model.dto.file.AvatarPresignRequest
import cn.esuny.orion.service.impl.FileServiceImpl
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.model.HeadObjectResponse
import software.amazon.awssdk.services.s3.model.CopyObjectRequest
import software.amazon.awssdk.services.s3.model.HeadObjectRequest
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import software.amazon.awssdk.services.s3.presigner.model.PresignedGetObjectRequest
import software.amazon.awssdk.services.s3.presigner.model.PresignedPutObjectRequest
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest
import java.net.URL
import java.time.Duration
import java.time.OffsetDateTime

class FileServiceTest {

    private lateinit var fileService: FileService
    private lateinit var s3Client: S3Client
    private lateinit var s3Presigner: S3Presigner
    private lateinit var ossProperties: OssProperties
    private lateinit var userMapper: UserMapper
    private lateinit var fileCleanupTaskService: FileCleanupTaskService

    @BeforeEach
    fun setup() {
        s3Client = mockk(relaxed = true)
        s3Presigner = mockk(relaxed = true)
        userMapper = mockk(relaxed = true)
        fileCleanupTaskService = mockk(relaxed = true)

        ossProperties = OssProperties(
            endpoint = "http://localhost:9000",
            accessKey = "test-access-key",
            secretKey = "test-secret-key",
            bucket = "test-bucket",
            region = "us-east-1",
            presignedExpiration = Duration.ofMinutes(5),
            maxFileSize = 5 * 1024 * 1024,
            allowedContentTypes = listOf("image/jpeg", "image/png", "image/webp", "image/gif")
        )

        fileService = FileServiceImpl(
            s3Client = s3Client,
            s3Presigner = s3Presigner,
            ossProperties = ossProperties,
            userMapper = userMapper,
            fileCleanupTaskService = fileCleanupTaskService
        )
    }

    @Test
    fun `presignAvatarUpload should generate presigned URL`() {
        // Given
        val userId = 123L
        val request = AvatarPresignRequest(fileName = "avatar.jpg", contentType = "image/jpeg")

        val presignResponse = mockk<PresignedPutObjectRequest>()
        every { presignResponse.url() } returns URL(
            "http://localhost:9000/test-bucket/avatar-staging/123/1691234567_abc123.jpg?X-Amz-Algorithm=..."
        )

        every { s3Presigner.presignPutObject(any<PutObjectPresignRequest>()) } returns presignResponse

        // When
        val response = fileService.presignAvatarUpload(userId, request)

        // Then
        assertNotNull(response.uploadUrl)
        assertTrue(response.objectKey.startsWith("avatar-staging/123/"))
        assertTrue(response.uploadUrl.contains(".jpg?"))
        assertEquals(300, response.expiresIn)

        verify { s3Presigner.presignPutObject(any<PutObjectPresignRequest>()) }
    }

    @Test
    fun `presignAvatarUpload should reject invalid content type`() {
        // Given
        val userId = 123L
        val request = AvatarPresignRequest(fileName = "file.exe", contentType = "application/exe")

        // When & Then
        val exception = assertThrows<BusinessException> {
            fileService.presignAvatarUpload(userId, request)
        }
        assertEquals(400, exception.code)
    }

    @Test
    fun `confirmAvatarUpload should update user avatar`() {
        // Given
        val userId = 123L
        val objectKey = "avatar-staging/123/1691234567_abc123.jpg"

        val user = cn.esuny.orion.model.entity.user.User(
            userId = userId,
            username = "testuser",
            email = "test@example.com",
            passwordHash = "hashed-password",
            nickname = "Test",
            avatarUrl = "",
            createdAt = OffsetDateTime.now(),
            updatedAt = OffsetDateTime.now()
        )

        every { s3Client.headObject(any<HeadObjectRequest>()) } returns HeadObjectResponse.builder()
            .contentType("image/jpeg")
            .contentLength(1024)
            .build()
        every { userMapper.selectByIdForUpdate(userId) } returns user
        every { userMapper.updateById(any<cn.esuny.orion.model.entity.user.User>()) } returns 1

        // When
        val response = fileService.confirmAvatarUpload(userId, objectKey)

        // Then
        assertNotNull(response.avatarUrl)
        verify { s3Client.copyObject(any<CopyObjectRequest>()) }
        verify { userMapper.updateById(match<cn.esuny.orion.model.entity.user.User> { it.avatarUrl.startsWith("avatars/123/") }) }
        verify { fileCleanupTaskService.enqueueStagingSource("test-bucket", objectKey) }
    }

    @Test
    fun `confirmAvatarUpload should reject final and foreign object key prefixes`() {
        // Given
        val userId = 123L
        val invalidObjectKeys = listOf(
            "avatars/123/file.jpg",
            "avatar-staging/456/file.jpg",
            "other/456/file.jpg"
        )

        invalidObjectKeys.forEach { invalidObjectKey ->
            // When & Then
            val exception = assertThrows<BusinessException> {
                fileService.confirmAvatarUpload(userId, invalidObjectKey)
            }
            assertEquals(403, exception.code)
        }

        verify(exactly = 0) { s3Client.headObject(any<HeadObjectRequest>()) }
    }

    @Test
    fun `getAvatarUrl should return presigned URL`() {
        // Given
        val userId = 123L
        val objectKey = "avatars/123/1691234567_abc123.jpg"

        val user = cn.esuny.orion.model.entity.user.User(
            userId = userId,
            username = "testuser",
            email = "test@example.com",
            passwordHash = "hashed-password",
            nickname = "Test",
            avatarUrl = objectKey,
            createdAt = OffsetDateTime.now(),
            updatedAt = OffsetDateTime.now()
        )

        val presignResponse = mockk<PresignedGetObjectRequest>()
        every { presignResponse.url() } returns URL(
            "http://localhost:9000/test-bucket/$objectKey?X-Amz-Algorithm=..."
        )

        every { userMapper.selectById(userId) } returns user
        every { s3Presigner.presignGetObject(any<GetObjectPresignRequest>()) } returns presignResponse

        // When
        val response = fileService.getAvatarUrl(userId)

        // Then
        assertNotNull(response)
        assertTrue(response.contains("avatars/123/"))
    }
}
