package cn.esuny.nutrimemo.internal

import cn.esuny.nutrimemo.config.OssProperties
import cn.esuny.nutrimemo.persistence.NutriRepository
import com.fasterxml.jackson.annotation.JsonProperty
import jakarta.validation.Valid
import jakarta.validation.constraints.NotNull
import org.springframework.http.HttpStatus
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken
import org.springframework.stereotype.Service
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController
import org.springframework.web.server.ResponseStatusException
import software.amazon.awssdk.services.s3.model.GetObjectRequest
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest
import java.time.OffsetDateTime
import java.util.UUID

data class CaptureAnalysisContextRequest(
    @field:NotNull @JsonProperty("subject_id") val subjectId: UUID,
    @field:NotNull @JsonProperty("capture_session_id") val captureSessionId: UUID,
    @field:NotNull @JsonProperty("meal_id") val mealId: Long,
    @field:NotNull @JsonProperty("task_id") val taskId: UUID,
)

data class CaptureAnalysisContextResponse(
    @JsonProperty("capture_session_id") val captureSessionId: UUID,
    @JsonProperty("meal_id") val mealId: Long,
    @JsonProperty("meal_type") val mealType: String,
    @JsonProperty("consumed_at") val consumedAt: OffsetDateTime,
    val timezone: String,
    @JsonProperty("image_urls") val imageUrls: List<ConfirmedImageContext>,
)

data class ConfirmedImageContext(
    @JsonProperty("content_type") val contentType: String,
    @JsonProperty("content_length") val contentLength: Long,
    @JsonProperty("captured_at") val capturedAt: OffsetDateTime?,
    val url: String,
    @JsonProperty("expires_in_seconds") val expiresInSeconds: Long,
)

@Service
class CaptureAnalysisContextService(
    private val repository: NutriRepository,
    private val presigner: S3Presigner,
    private val oss: OssProperties,
) {
    fun get(request: CaptureAnalysisContextRequest): CaptureAnalysisContextResponse {
        val session = repository.session(request.captureSessionId, request.subjectId)
            ?: throw ResponseStatusException(HttpStatus.NOT_FOUND)
        val meal = repository.meal(request.mealId, request.subjectId)
            ?.takeIf { it.captureSessionId == session.captureSessionId && it.status == "active" }
            ?: throw ResponseStatusException(HttpStatus.NOT_FOUND)
        val images = repository.images(session.captureSessionId)
            .filter { it.status == "confirmed" }
            .map { image ->
                val signed = presigner.presignGetObject(
                    GetObjectPresignRequest.builder()
                        .signatureDuration(oss.presignedExpiration)
                        .getObjectRequest(GetObjectRequest.builder().bucket(image.bucket).key(image.objectKey).build())
                        .build(),
                )
                ConfirmedImageContext(
                    contentType = image.contentType,
                    contentLength = image.contentLength,
                    capturedAt = image.capturedAt,
                    url = signed.url().toString(),
                    expiresInSeconds = oss.presignedExpiration.seconds,
                )
            }
        if (images.isEmpty()) throw ResponseStatusException(HttpStatus.CONFLICT, "No confirmed capture images")
        return CaptureAnalysisContextResponse(
            session.captureSessionId,
            meal.mealId,
            meal.mealType,
            meal.consumedAt,
            meal.timezone,
            images,
        )
    }
}

@RestController
@RequestMapping("/internal/v1/analysis-context")
class CaptureAnalysisContextController(
    private val service: CaptureAnalysisContextService,
    private val security: NutriInternalSecurityProperties,
) {
    @PostMapping("/capture")
    fun getCaptureContext(
        @Valid @RequestBody request: CaptureAnalysisContextRequest,
        authentication: JwtAuthenticationToken,
    ): CaptureAnalysisContextResponse {
        val caller = authentication.token.getClaimAsString("azp")
            ?: authentication.token.getClaimAsString("client_id")
        require(caller == security.allowedHealthMindClientId) { "Internal caller is not HealthMind" }
        return service.get(request)
    }
}
