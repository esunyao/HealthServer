package cn.esuny.orion.model.entity.user

import cn.esuny.orion.model.typehandler.PgJsonbTypeHandler
import com.baomidou.mybatisplus.annotation.IdType
import com.baomidou.mybatisplus.annotation.TableField
import com.baomidou.mybatisplus.annotation.TableId
import com.baomidou.mybatisplus.annotation.TableName
import java.math.BigDecimal
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

@TableName("orion.user_body_measurements")
data class UserBodyMeasurement(
    @TableId(type = IdType.INPUT) val measurementId: Long,
    val userId: UUID,
    val measuredAt: OffsetDateTime = OffsetDateTime.now(),
    val heightCm: BigDecimal? = null,
    val weightKg: BigDecimal? = null,
    val bodyFatPercentage: BigDecimal? = null,
    val waistCm: BigDecimal? = null,
    val systolicBp: Short? = null,
    val diastolicBp: Short? = null,
    val restingHeartRate: Short? = null,
    val source: String = "manual",
    val sourceReference: String? = null,
    val notes: String? = null,
    val createdAt: OffsetDateTime = OffsetDateTime.now(),
    val updatedAt: OffsetDateTime = OffsetDateTime.now()
)

@TableName("orion.user_health_goals")
data class UserHealthGoal(
    @TableId(type = IdType.INPUT) val goalId: Long,
    val userId: UUID,
    val goalType: String,
    val targetWeightKg: BigDecimal? = null,
    val targetBodyFatPercentage: BigDecimal? = null,
    val priority: Short = 1,
    val status: String = "active",
    val startedOn: LocalDate = LocalDate.now(),
    val targetDate: LocalDate? = null,
    val completedAt: OffsetDateTime? = null,
    val notes: String? = null,
    val createdAt: OffsetDateTime = OffsetDateTime.now(),
    val updatedAt: OffsetDateTime = OffsetDateTime.now()
)

@TableName("orion.user_allergies")
data class UserAllergy(
    @TableId(type = IdType.INPUT) val allergyId: Long,
    val userId: UUID,
    val allergenCode: String,
    val allergenName: String,
    val severity: String? = null,
    val reactionDescription: String? = null,
    val diagnosisStatus: String = "self_reported",
    val recordedOn: LocalDate? = null,
    val active: Boolean = true,
    val notes: String? = null,
    val createdAt: OffsetDateTime = OffsetDateTime.now(),
    val updatedAt: OffsetDateTime = OffsetDateTime.now()
)

@TableName("orion.user_medical_conditions")
data class UserMedicalCondition(
    @TableId(type = IdType.INPUT) val conditionId: Long,
    val userId: UUID,
    val conditionCode: String,
    val conditionName: String,
    val status: String = "active",
    val diagnosedOn: LocalDate? = null,
    val resolvedOn: LocalDate? = null,
    val source: String = "self_reported",
    val notes: String? = null,
    val createdAt: OffsetDateTime = OffsetDateTime.now(),
    val updatedAt: OffsetDateTime = OffsetDateTime.now()
)

@TableName("orion.user_dietary_restrictions")
data class UserDietaryRestriction(
    @TableId(type = IdType.INPUT) val restrictionId: Long,
    val userId: UUID,
    val restrictionCode: String,
    val restrictionName: String,
    val category: String,
    val source: String = "self_reported",
    val active: Boolean = true,
    val startsOn: LocalDate? = null,
    val endsOn: LocalDate? = null,
    val notes: String? = null,
    val createdAt: OffsetDateTime = OffsetDateTime.now(),
    val updatedAt: OffsetDateTime = OffsetDateTime.now()
)

@TableName("orion.user_cuisine_preferences")
data class UserCuisinePreference(
    @TableId(type = IdType.INPUT) val userId: UUID,
    val cuisineCode: String,
    val cuisineName: String,
    val preferenceScore: Short = 0,
    val notes: String? = null,
    val createdAt: OffsetDateTime = OffsetDateTime.now(),
    val updatedAt: OffsetDateTime = OffsetDateTime.now()
)

@TableName(value = "orion.clinical_observations", autoResultMap = true)
data class ClinicalObservation(
    @TableId(type = IdType.INPUT) val observationId: Long,
    val userId: UUID,
    val observationCode: String,
    val observationName: String,
    val valueNumeric: BigDecimal? = null,
    val valueText: String? = null,
    val unit: String? = null,
    val referenceLow: BigDecimal? = null,
    val referenceHigh: BigDecimal? = null,
    val interpretation: String = "unknown",
    val observedAt: OffsetDateTime,
    val source: String = "self_reported",
    val reportObjectKey: String? = null,
    @TableField(typeHandler = PgJsonbTypeHandler::class) val metadata: String = "{}",
    val createdAt: OffsetDateTime = OffsetDateTime.now()
)

@TableName("orion.user_consents")
data class UserConsent(
    @TableId(type = IdType.INPUT) val consentId: Long,
    val userId: UUID,
    val consentType: String,
    val policyVersion: String,
    val granted: Boolean = true,
    val recordedAt: OffsetDateTime = OffsetDateTime.now(),
    val source: String = "mobile",
    val clientIp: String? = null,
    val userAgent: String? = null,
    val createdAt: OffsetDateTime = OffsetDateTime.now()
)
