package cn.esuny.orion.model.entity.user

import cn.esuny.orion.model.enums.user.ActivityLevel
import cn.esuny.orion.model.enums.user.Gender
import com.baomidou.mybatisplus.annotation.IdType
import com.baomidou.mybatisplus.annotation.TableId
import com.baomidou.mybatisplus.annotation.TableName
import java.math.BigDecimal
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

/** 用户当前基础健康画像，与业务用户一对一。 */
@TableName("orion.user_profiles")
data class UserProfile(
    @TableId(type = IdType.INPUT)
    val userId: UUID,
    val birthDate: LocalDate? = null,
    val gender: Gender? = null,
    val heightCm: BigDecimal? = null,
    val activityLevel: ActivityLevel? = null,
    val dailyWaterTargetMl: Int = 2000,
    val profileCompletedAt: OffsetDateTime? = null,
    val createdAt: OffsetDateTime = OffsetDateTime.now(),
    val updatedAt: OffsetDateTime = OffsetDateTime.now()
)
