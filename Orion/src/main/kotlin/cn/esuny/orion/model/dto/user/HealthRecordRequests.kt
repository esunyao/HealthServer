package cn.esuny.orion.model.dto.user

import jakarta.validation.Valid
import jakarta.validation.constraints.DecimalMax
import jakarta.validation.constraints.DecimalMin
import jakarta.validation.constraints.Max
import jakarta.validation.constraints.Min
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.NotEmpty
import jakarta.validation.constraints.Size
import java.math.BigDecimal
import java.time.LocalDate
import java.time.OffsetDateTime

data class BodyMeasurementRequest(
    val measuredAt: OffsetDateTime? = null,
    @field:DecimalMin("50.0") @field:DecimalMax("300.0") val heightCm: BigDecimal? = null,
    @field:DecimalMin("10.0") @field:DecimalMax("500.0") val weightKg: BigDecimal? = null,
    @field:DecimalMin("0.0") @field:DecimalMax("100.0") val bodyFatPercentage: BigDecimal? = null,
    @field:DecimalMin("20.0") @field:DecimalMax("300.0") val waistCm: BigDecimal? = null,
    @field:Min(40) @field:Max(300) val systolicBp: Short? = null,
    @field:Min(20) @field:Max(200) val diastolicBp: Short? = null,
    @field:Min(20) @field:Max(250) val restingHeartRate: Short? = null,
    val source: String? = null,
    @field:Size(max = 255) val sourceReference: String? = null,
    @field:Size(max = 500) val notes: String? = null
)

data class HealthGoalRequest(
    @field:NotBlank @field:Size(max = 32) val goalType: String,
    @field:DecimalMin("10.0") @field:DecimalMax("500.0") val targetWeightKg: BigDecimal? = null,
    @field:DecimalMin("0.0") @field:DecimalMax("100.0") val targetBodyFatPercentage: BigDecimal? = null,
    @field:Min(1) @field:Max(10) val priority: Short? = null,
    val status: String? = null,
    val startedOn: LocalDate? = null,
    val targetDate: LocalDate? = null,
    @field:Size(max = 500) val notes: String? = null
)

data class AllergyRequest(
    @field:NotBlank @field:Size(max = 64) val allergenCode: String,
    @field:NotBlank @field:Size(max = 100) val allergenName: String,
    val severity: String? = null,
    @field:Size(max = 500) val reactionDescription: String? = null,
    val diagnosisStatus: String? = null,
    val recordedOn: LocalDate? = null,
    val active: Boolean? = null,
    @field:Size(max = 500) val notes: String? = null
)

data class MedicalConditionRequest(
    @field:NotBlank @field:Size(max = 64) val conditionCode: String,
    @field:NotBlank @field:Size(max = 150) val conditionName: String,
    val status: String? = null,
    val diagnosedOn: LocalDate? = null,
    val resolvedOn: LocalDate? = null,
    val source: String? = null,
    val notes: String? = null
)

data class DietaryRestrictionRequest(
    @field:NotBlank @field:Size(max = 64) val restrictionCode: String,
    @field:NotBlank @field:Size(max = 100) val restrictionName: String,
    @field:NotBlank val category: String,
    val source: String? = null,
    val active: Boolean? = null,
    val startsOn: LocalDate? = null,
    val endsOn: LocalDate? = null,
    @field:Size(max = 500) val notes: String? = null
)

data class CuisinePreferenceRequest(
    @field:NotBlank @field:Size(max = 64) val cuisineCode: String,
    @field:NotBlank @field:Size(max = 100) val cuisineName: String,
    @field:Min(-2) @field:Max(2) val preferenceScore: Short = 0,
    @field:Size(max = 500) val notes: String? = null
)

data class ReplaceCuisinePreferencesRequest(@field:NotEmpty val preferences: List<@Valid CuisinePreferenceRequest>)

data class ClinicalObservationRequest(
    @field:NotBlank @field:Size(max = 64) val observationCode: String,
    @field:NotBlank @field:Size(max = 150) val observationName: String,
    val valueNumeric: BigDecimal? = null,
    @field:Size(max = 500) val valueText: String? = null,
    @field:Size(max = 32) val unit: String? = null,
    val referenceLow: BigDecimal? = null,
    val referenceHigh: BigDecimal? = null,
    val interpretation: String? = null,
    val observedAt: OffsetDateTime? = null,
    val source: String? = null,
    @field:Size(max = 1024) val reportObjectKey: String? = null,
    val metadata: String? = null
)

data class UserConsentRequest(
    @field:NotBlank @field:Size(max = 64) val consentType: String,
    @field:NotBlank @field:Size(max = 32) val policyVersion: String,
    val granted: Boolean = true,
    val source: String? = null
)
