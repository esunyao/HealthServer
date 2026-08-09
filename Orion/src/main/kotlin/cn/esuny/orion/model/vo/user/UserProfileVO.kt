package cn.esuny.orion.model.vo.user

import cn.esuny.orion.model.enums.user.ActivityLevel
import cn.esuny.orion.model.enums.user.Gender
import java.math.BigDecimal
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

data class UserProfileVO(
    val userId: UUID,
    val birthDate: LocalDate?,
    val gender: Gender?,
    val heightCm: BigDecimal?,
    val activityLevel: ActivityLevel?,
    val dailyWaterTargetMl: Int,
    val profileCompletedAt: OffsetDateTime?,
    val createdAt: OffsetDateTime,
    val updatedAt: OffsetDateTime
)
