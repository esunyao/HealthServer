package cn.esuny.orion.model.dto.user

import cn.esuny.orion.model.enums.user.ActivityLevel
import cn.esuny.orion.model.enums.user.Gender
import cn.esuny.orion.model.enums.user.HealthGoal
import java.math.BigDecimal

/**
 * 更新用户画像请求体（全部字段可选，仅更新非 null 字段）
 */
data class UserProfileUpdateRequest(
    val age: Int? = null,
    val gender: Gender? = null,
    val heightCm: BigDecimal? = null,
    val weightKg: BigDecimal? = null,
    val activityLevel: ActivityLevel? = null,
    val healthGoal: HealthGoal? = null,
    val allergies: List<String>? = null,
    val dietaryRestrictions: List<String>? = null,
    val medicalConditions: List<String>? = null,
    val dailyWaterMl: Int? = null,
    val preferredCuisine: List<String>? = null
)
