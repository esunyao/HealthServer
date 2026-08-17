package cn.esuny.nutrimemo.model

import jakarta.validation.Valid
import jakarta.validation.constraints.DecimalMax
import jakarta.validation.constraints.DecimalMin
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.NotEmpty
import jakarta.validation.constraints.NotNull
import jakarta.validation.constraints.Pattern
import jakarta.validation.constraints.Size
import java.math.BigDecimal
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

data class CaptureSessionCreateRequest(@field:NotBlank @field:Size(max = 64) val timezone: String)
data class CaptureImagePresignRequest(
    @field:NotBlank @field:Size(max = 255) val fileName: String,
    @field:Pattern(regexp = "image/(jpeg|png|webp)") val contentType: String,
    @field:DecimalMin("1") @field:DecimalMax("10485760") val contentLength: Long,
    val capturedAt: OffsetDateTime? = null
)
data class MealNutrientInput(@field:NotBlank @field:Size(max = 64) val nutrientCode: String, @field:NotNull @field:DecimalMin("0") val amount: BigDecimal)
data class MealCorrectionItemInput(
    val itemId: Long? = null,
    @field:NotBlank @field:Size(max = 150) val displayName: String,
    @field:DecimalMin("0.001") @field:DecimalMax("100000") val estimatedWeightG: BigDecimal? = null,
    @field:Size(max = 500) val notes: String? = null,
    @field:NotEmpty @field:Size(max = 100) val nutrients: List<@Valid MealNutrientInput>
)
data class MealCorrectionRequest(
    @field:NotBlank val mealType: String,
    @field:NotNull val consumedAt: OffsetDateTime,
    @field:NotBlank @field:Size(max = 64) val timezone: String,
    @field:Size(max = 1000) val notes: String? = null,
    @field:NotEmpty @field:Size(max = 100) val items: List<@Valid MealCorrectionItemInput>
)

data class NutrientValue(val nutrientCode: String, val nutrientName: String, val unit: String, val amount: BigDecimal)
data class PresignedUrlView(val uploadUrl: String, val objectKey: String, val expiresInSeconds: Long, val requiredHeaders: Map<String, String>)
data class CapturePolicyView(val maxImageCount: Int, val maxFileSizeBytes: Long, val allowedContentTypes: List<String>, val sessionExpiresInSeconds: Long)
data class CaptureImageView(val imageId: Long, val slotNo: Int, val objectKey: String, val contentType: String, val contentLength: Long, val capturedAt: OffsetDateTime?, val status: String, val createdAt: OffsetDateTime)
data class CaptureSessionView(val captureSessionId: UUID, val status: String, val timezone: String, val maxImageCount: Int, val expiresAt: OffsetDateTime, val analysisRequestedAt: OffsetDateTime?, val images: List<CaptureImageView>, val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime)
data class MealItemView(val itemId: Long, val sequenceNo: Int, val displayName: String, val estimatedWeightG: BigDecimal?, val confidence: BigDecimal?, val dataSource: String, val userCorrected: Boolean, val notes: String?, val nutrients: List<NutrientValue>)
data class MealView(val mealId: Long, val captureSessionId: UUID, val mealType: String, val consumedAt: OffsetDateTime, val timezone: String, val localDate: LocalDate, val notes: String?, val items: List<MealItemView>, val nutrients: List<NutrientValue>, val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime)
data class MealHistoryItemView(val mealId: Long, val mealType: String, val consumedAt: OffsetDateTime, val localDate: LocalDate, val notes: String?, val nutrients: List<NutrientValue>)
data class PageResult<T>(val items: List<T>, val page: Int, val pageSize: Int, val total: Long)
data class DailyMealBreakdown(val mealType: String, val mealCount: Int, val nutrients: List<NutrientValue>)
data class DailySummaryView(val localDate: LocalDate, val mealCount: Int, val nutrients: List<NutrientValue>, val mealBreakdown: List<DailyMealBreakdown>, val updatedAt: OffsetDateTime)
data class DailyTrendView(val dateFrom: LocalDate, val dateTo: LocalDate, val days: List<DailySummaryView>)

data class NutrientDefinition(val nutrientId: Long, val nutrientCode: String, val nutrientName: String, val unit: String, val active: Boolean)
data class CaptureSessionRecord(val captureSessionId: UUID, val userId: UUID, val clientRequestId: UUID, val status: String, val timezone: String, val maxImageCount: Int, val expiresAt: OffsetDateTime, val analysisRequestedAt: OffsetDateTime?, val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime)
data class CaptureImageRecord(val imageId: Long, val captureSessionId: UUID, val slotNo: Int, val bucket: String, val objectKey: String, val contentType: String, val contentLength: Long, val capturedAt: OffsetDateTime?, val status: String, val confirmedAt: OffsetDateTime?, val createdAt: OffsetDateTime)
data class MealRecord(val mealId: Long, val captureSessionId: UUID, val userId: UUID, val mealType: String, val consumedAt: OffsetDateTime, val timezone: String, val localDate: LocalDate, val notes: String?, val status: String, val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime)
data class MealItemRecord(val itemId: Long, val mealId: Long, val sequenceNo: Int, val displayName: String, val estimatedWeightG: BigDecimal?, val confidence: BigDecimal?, val dataSource: String, val userCorrected: Boolean, val notes: String?)
