package cn.esuny.nutrimemo.internal

import cn.esuny.nutrimemo.config.OssProperties
import cn.esuny.nutrimemo.model.CaptureImageRecord
import cn.esuny.nutrimemo.model.CaptureSessionRecord
import cn.esuny.nutrimemo.model.MealRecord
import cn.esuny.nutrimemo.persistence.NutriRepository
import com.fasterxml.jackson.annotation.JsonInclude
import io.mockk.every
import io.mockk.mockk
import org.junit.jupiter.api.Test
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest
import software.amazon.awssdk.services.s3.presigner.model.PresignedGetObjectRequest
import java.net.URI
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertEquals

class CaptureAnalysisContextTest {
    private val sessionId = UUID.fromString("33333333-3333-4333-8333-333333333333")
    private val userId = UUID.fromString("44444444-4444-4444-8444-444444444444")
    private val taskId = UUID.fromString("55555555-5555-4555-8555-555555555555")
    private val now = OffsetDateTime.parse("2026-10-26T12:30:00+08:00")

    @Test
    fun `capture context returns notes persisted on the meal`() {
        val response = responseFor(notes = "米饭约半碗，少油")

        assertEquals("米饭约半碗，少油", response.notes)
    }

    @Test
    fun `capture context preserves null and empty notes for the agent boundary`() {
        assertEquals(null, responseFor(notes = null).notes)
        assertEquals("", responseFor(notes = "").notes)
    }

    @Test
    fun `old release schema compatibility omits notes`() {
        val response = responseFor(notes = "must not leak into v1.0 schema", includeMealNotes = false)
        val annotation = CaptureAnalysisContextResponse::class.java.getMethod("getNotes")
            .getAnnotation(JsonInclude::class.java)

        assertEquals(null, response.notes)
        assertEquals(JsonInclude.Include.NON_NULL, annotation.value)
    }

    private fun responseFor(notes: String?, includeMealNotes: Boolean = true): CaptureAnalysisContextResponse {
        val repository = mockk<NutriRepository>()
        every { repository.session(sessionId, userId) } returns CaptureSessionRecord(
            captureSessionId = sessionId,
            userId = userId,
            clientRequestId = UUID.fromString("66666666-6666-4666-8666-666666666666"),
            status = "submitted",
            timezone = "Asia/Shanghai",
            maxImageCount = 10,
            expiresAt = now.plusHours(1),
            analysisRequestedAt = now,
            createdAt = now,
            updatedAt = now,
        )
        every { repository.meal(42, userId) } returns MealRecord(
            mealId = 42,
            captureSessionId = sessionId,
            userId = userId,
            mealType = "lunch",
            consumedAt = now,
            timezone = "Asia/Shanghai",
            localDate = now.toLocalDate(),
            notes = notes,
            analysisStatus = "analysing",
            status = "active",
            createdAt = now,
            updatedAt = now,
        )
        every { repository.images(sessionId) } returns listOf(
            CaptureImageRecord(
                imageId = 1,
                captureSessionId = sessionId,
                slotNo = 1,
                bucket = "nutri",
                objectKey = "capture/meal-1.jpg",
                contentType = "image/jpeg",
                contentLength = 128,
                capturedAt = now,
                status = "confirmed",
                confirmedAt = now,
                createdAt = now,
            ),
        )

        val presigner = mockk<S3Presigner>()
        val presigned = mockk<PresignedGetObjectRequest>()
        every { presigner.presignGetObject(any<GetObjectPresignRequest>()) } returns presigned
        every { presigned.url() } returns URI.create("https://media.example.test/meal-1.jpg").toURL()

        return CaptureAnalysisContextService(
            repository,
            presigner,
            OssProperties(
                endpoint = "https://storage.example.test",
                presignedAddr = "https://media.example.test",
                accessKey = "test",
                secretKey = "test",
                bucket = "nutri",
            ),
        ).get(
            CaptureAnalysisContextRequest(
                subjectId = userId,
                captureSessionId = sessionId,
                mealId = 42,
                taskId = taskId,
                includeMealNotes = includeMealNotes,
            ),
        )
    }
}
