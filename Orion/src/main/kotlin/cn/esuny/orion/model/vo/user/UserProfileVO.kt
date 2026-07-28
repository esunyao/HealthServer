package cn.esuny.orion.model.vo.user

import cn.esuny.orion.model.enums.user.ActivityLevel
import cn.esuny.orion.model.enums.user.Gender
import cn.esuny.orion.model.enums.user.HealthGoal
import java.math.BigDecimal
import java.time.OffsetDateTime
import java.util.UUID

/**
 * 用户画像视图对象（返回给客户端）
 */
data class UserProfileVO(
    val profileId: UUID,
    val userId: UUID,
    val age: Short?,
    val gender: Gender?,
    val heightCm: BigDecimal?,
    val weightKg: BigDecimal?,
    val bmi: BigDecimal?,
    val activityLevel: ActivityLevel?,
    val healthGoal: HealthGoal?,
    val allergies: List<String>,
    val dietaryRestrictions: List<String>,
    val medicalConditions: List<String>,
    val dailyWaterMl: Int,
    val preferredCuisine: List<String>,
    val createdAt: OffsetDateTime,
    val updatedAt: OffsetDateTime
)
