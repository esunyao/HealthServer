package cn.esuny.orion.internal.nutrition

import com.fasterxml.jackson.annotation.JsonProperty
import jakarta.validation.constraints.NotNull
import java.math.BigDecimal
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

data class NutritionAiContextRequest(
    @field:NotNull @JsonProperty("subject_id") val subjectId: UUID,
    @field:NotNull @JsonProperty("task_id") val taskId: UUID,
)

data class NutritionAiContextResponse(
    @JsonProperty("subject_id") val subjectId: UUID,
    @JsonProperty("age_years") val ageYears: Int?,
    val gender: String?,
    @JsonProperty("height_cm") val heightCm: BigDecimal?,
    @JsonProperty("latest_measurement") val latestMeasurement: MinimalMeasurement?,
    @JsonProperty("active_goals") val activeGoals: List<MinimalGoal>,
    val allergies: List<MinimalAllergy>,
    @JsonProperty("medical_conditions") val medicalConditions: List<MinimalCondition>,
    @JsonProperty("dietary_restrictions") val dietaryRestrictions: List<MinimalRestriction>,
    @JsonProperty("cuisine_preferences") val cuisinePreferences: List<MinimalCuisinePreference>,
)

data class MinimalMeasurement(
    @JsonProperty("measured_at") val measuredAt: OffsetDateTime,
    @JsonProperty("height_cm") val heightCm: BigDecimal?,
    @JsonProperty("weight_kg") val weightKg: BigDecimal?,
    @JsonProperty("body_fat_percentage") val bodyFatPercentage: BigDecimal?,
    @JsonProperty("waist_cm") val waistCm: BigDecimal?,
)

data class MinimalGoal(
    @JsonProperty("goal_type") val goalType: String,
    @JsonProperty("target_weight_kg") val targetWeightKg: BigDecimal?,
    @JsonProperty("target_body_fat_percentage") val targetBodyFatPercentage: BigDecimal?,
    val priority: Short,
    @JsonProperty("target_date") val targetDate: LocalDate?,
)

data class MinimalAllergy(
    @JsonProperty("allergen_code") val allergenCode: String,
    @JsonProperty("allergen_name") val allergenName: String,
    val severity: String?,
)

data class MinimalCondition(
    @JsonProperty("condition_code") val conditionCode: String,
    @JsonProperty("condition_name") val conditionName: String,
)

data class MinimalRestriction(
    @JsonProperty("restriction_code") val restrictionCode: String,
    @JsonProperty("restriction_name") val restrictionName: String,
    val category: String,
)

data class MinimalCuisinePreference(
    @JsonProperty("cuisine_code") val cuisineCode: String,
    @JsonProperty("cuisine_name") val cuisineName: String,
    @JsonProperty("preference_score") val preferenceScore: Short,
)
