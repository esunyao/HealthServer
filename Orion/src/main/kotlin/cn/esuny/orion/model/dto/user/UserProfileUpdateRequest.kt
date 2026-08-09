package cn.esuny.orion.model.dto.user

import cn.esuny.orion.model.enums.user.ActivityLevel
import cn.esuny.orion.model.enums.user.Gender
import jakarta.validation.constraints.DecimalMax
import jakarta.validation.constraints.DecimalMin
import jakarta.validation.constraints.Max
import jakarta.validation.constraints.Min
import java.math.BigDecimal
import java.time.LocalDate

data class UserProfileUpdateRequest(
    val birthDate: LocalDate? = null,
    val gender: Gender? = null,
    @field:DecimalMin("50.0") @field:DecimalMax("300.0")
    val heightCm: BigDecimal? = null,
    val activityLevel: ActivityLevel? = null,
    @field:Min(0) @field:Max(10000)
    val dailyWaterTargetMl: Int? = null
)
