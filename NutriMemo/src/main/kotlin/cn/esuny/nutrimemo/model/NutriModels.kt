package cn.esuny.nutrimemo.model

import jakarta.validation.Valid
import jakarta.validation.constraints.DecimalMax
import jakarta.validation.constraints.DecimalMin
import jakarta.validation.constraints.Max
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.NotEmpty
import jakarta.validation.constraints.NotNull
import jakarta.validation.constraints.Pattern
import jakarta.validation.constraints.Size
import java.math.BigDecimal
import java.time.LocalDate
import java.time.OffsetDateTime

data class NutrientInput(@field:NotBlank @field:Size(max = 64) val nutrientCode: String, @field:NotNull @field:DecimalMin("0") val amount: BigDecimal)
data class CustomFoodRequest(
    @field:NotBlank @field:Size(max = 150) val name: String,
    @field:NotBlank val foodType: String,
    @field:Size(max = 100) val brandName: String? = null,
    @field:DecimalMin("0.01") @field:DecimalMax("10000") val defaultServingG: BigDecimal? = null,
    @field:Size(max = 20) val aliases: List<@NotBlank @Size(max = 100) String> = emptyList(),
    @field:NotEmpty @field:Size(max = 100) val nutrients: List<@Valid NutrientInput>
)
data class MealItemInput(@field:NotNull val foodId: Long, @field:DecimalMin("0.01") @field:DecimalMax("100000") val consumedAmountG: BigDecimal, @field:Size(max = 150) val displayName: String? = null, @field:Size(max = 500) val notes: String? = null)
data class MealUpsertRequest(
    @field:NotBlank val mealType: String, @field:NotNull val consumedAt: OffsetDateTime,
    @field:NotBlank @field:Size(max = 64) val timezone: String, @field:Size(max = 64) val scenario: String? = null,
    @field:NotBlank val entrySource: String, @field:Size(max = 1000) val notes: String? = null,
    @field:NotEmpty @field:Size(max = 100) val items: List<@Valid MealItemInput>
)
data class MealImagePresignRequest(@field:NotBlank @field:Size(max = 255) val fileName: String, @field:Pattern(regexp = "image/(jpeg|png|webp)") val contentType: String, @field:DecimalMin("1") @field:DecimalMax("10485760") val contentLength: Long, val capturedAt: OffsetDateTime? = null)
data class MealImageConfirmRequest(@field:NotBlank @field:Size(max = 1024) val objectKey: String, val capturedAt: OffsetDateTime? = null)

data class NutrientValue(val nutrientCode: String, val nutrientName: String, val unit: String, val amount: BigDecimal)
data class FoodView(val foodId: Long, val scope: String, val name: String, val foodType: String, val brandName: String?, val defaultServingG: BigDecimal?, val aliases: List<String>, val active: Boolean, val nutrients: List<NutrientValue>, val version: Int, val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime)
data class MealItemView(val itemId: Long, val sequenceNo: Int, val foodId: Long?, val foodVersion: Int?, val foodNameSnapshot: String, val consumedAmountG: BigDecimal, val notes: String?, val nutrientSnapshots: List<NutrientValue>, val createdAt: OffsetDateTime)
data class MealImageView(val imageId: Long, val objectKey: String, val contentType: String, val capturedAt: OffsetDateTime?, val status: String, val createdAt: OffsetDateTime)
data class MealView(val mealId: Long, val mealType: String, val consumedAt: OffsetDateTime, val timezone: String, val localDate: LocalDate, val scenario: String?, val entrySource: String, val notes: String?, val status: String, val items: List<MealItemView>, val images: List<MealImageView>, val nutrients: List<NutrientValue>, val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime)
data class PageResult<T>(val items: List<T>, val page: Int, val pageSize: Int, val total: Long)
data class PresignedUrlView(val uploadUrl: String, val objectKey: String, val expiresInSeconds: Long, val requiredHeaders: Map<String, String>)
data class DailyMealBreakdown(val mealType: String, val mealCount: Int, val nutrients: List<NutrientValue>)
data class DailySummaryView(val localDate: LocalDate, val mealCount: Int, val nutrients: List<NutrientValue>, val mealBreakdown: List<DailyMealBreakdown>, val updatedAt: OffsetDateTime)
data class DailyTrendView(val dateFrom: LocalDate, val dateTo: LocalDate, val days: List<DailySummaryView>)

data class FoodRecord(val foodId: Long, val ownerUserId: java.util.UUID?, val scope: String, val name: String, val foodType: String, val brandName: String?, val defaultServingG: BigDecimal?, val version: Int, val active: Boolean, val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime)
data class NutrientDefinition(val nutrientId: Long, val nutrientCode: String, val nutrientName: String, val unit: String, val active: Boolean)
data class FoodNutrientRecord(val foodId: Long, val nutrientId: Long, val amountPer100g: BigDecimal, val dataSource: String = "user_manual")
data class MealRecord(val mealId: Long, val userId: java.util.UUID, val mealType: String, val consumedAt: OffsetDateTime, val timezone: String, val localDate: LocalDate, val scenario: String?, val entrySource: String, val notes: String?, val status: String, val idempotencyKey: java.util.UUID, val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime)
data class MealItemRecord(val itemId: Long, val mealId: Long, val sequenceNo: Int, val foodId: Long?, val foodVersion: Int?, val foodNameSnapshot: String, val consumedAmountG: BigDecimal, val notes: String?, val createdAt: OffsetDateTime)
data class MealImageRecord(val imageId: Long, val mealId: Long, val userId: java.util.UUID, val bucket: String, val objectKey: String, val contentType: String, val contentLength: Long, val capturedAt: OffsetDateTime?, val status: String, val confirmedAt: OffsetDateTime?, val createdAt: OffsetDateTime)
