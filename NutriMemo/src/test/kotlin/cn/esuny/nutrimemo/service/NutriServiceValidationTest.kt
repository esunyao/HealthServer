package cn.esuny.nutrimemo.service

import cn.esuny.nutrimemo.config.CaptureProperties
import cn.esuny.nutrimemo.config.OssProperties
import cn.esuny.nutrimemo.handler.BusinessException
import cn.esuny.nutrimemo.identity.AuthenticatedUser
import cn.esuny.nutrimemo.model.CaptureSessionCreateRequest
import cn.esuny.nutrimemo.persistence.NutriRepository
import io.mockk.mockk
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import java.time.Duration
import java.util.UUID
import kotlin.test.assertEquals

class NutriServiceValidationTest {
    private val service = NutriService(
        mockk<NutriRepository>(), SnowflakeIdGenerator(), mockk<S3Client>(), mockk<S3Presigner>(),
        OssProperties("https://storage.example", "https://storage.example", "a", "s", "nutri"),
        CaptureProperties(Duration.ofHours(24), Duration.ofMinutes(15))
    )

    @Test
    fun `rejects non IANA timezone before creating a capture session`() {
        val error = assertThrows<BusinessException> { service.createCaptureSession(AuthenticatedUser(UUID.randomUUID()), UUID.randomUUID(), CaptureSessionCreateRequest("CST")) }
        assertEquals(400, error.code)
    }

    @Test
    fun `capture policy exposes ten image limit and one day retention`() {
        val policy = service.capturePolicy()
        assertEquals(10, policy.maxImageCount)
        assertEquals(86_400, policy.sessionExpiresInSeconds)
        assertEquals(5, policy.maxDraftSessionCount)
        assertEquals(86_400, policy.draftExpiresInSeconds)
    }
}
