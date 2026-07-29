package cn.esuny.orion.model.entity.user

import cn.esuny.orion.model.enums.user.ActivityLevel
import cn.esuny.orion.model.enums.user.Gender
import cn.esuny.orion.model.enums.user.HealthGoal
import cn.esuny.orion.model.typehandler.PgStringArrayTypeHandler
import com.baomidou.mybatisplus.annotation.IdType

import com.baomidou.mybatisplus.annotation.TableField
import com.baomidou.mybatisplus.annotation.TableId
import com.baomidou.mybatisplus.annotation.TableName
import java.math.BigDecimal
import java.time.OffsetDateTime
import java.util.UUID

/**
 * 用户画像 — 个人身体数据、健康目标、饮食偏好和医疗限制
 *
 * 与 users 1:1 关系，级联删除。
 */
@TableName("\"User\".user_profiles")
data class UserProfile(
    /** 画像记录唯一标识 */
    @TableId(type=IdType.ASSIGN_ID)
    val profileId: Long? = null,

    /** 关联用户，1:1 关系 */
    var userId: Long,

    /** 年龄，限制合理范围 10–120 */
    val age: Short? = null,

    /** 性别：male / female / other */
    val gender: Gender? = null,

    /** 身高（厘米），精确到 0.1 */
    val heightCm: BigDecimal? = null,

    /** 体重（千克），精确到 0.1 */
    val weightKg: BigDecimal? = null,

    /** BMI 指数，由触发器自动计算 */
    val bmi: BigDecimal? = null,

    /** 活动水平 */
    val activityLevel: ActivityLevel? = null,

    /** 健康目标 */
    val healthGoal: HealthGoal? = null,

    /** 过敏原列表（PostgreSQL TEXT[]） */
    @TableField(typeHandler = PgStringArrayTypeHandler::class)
    val allergies: List<String> = emptyList(),

    /** 饮食限制（PostgreSQL TEXT[]），如素食、清真、无麸质 */
    @TableField(typeHandler = PgStringArrayTypeHandler::class)
    val dietaryRestrictions: List<String> = emptyList(),

    /** 医疗状况（PostgreSQL TEXT[]），如糖尿病、高血压、痛风 */
    @TableField(typeHandler = PgStringArrayTypeHandler::class)
    val medicalConditions: List<String> = emptyList(),

    /** 每日饮水量目标（毫升） */
    val dailyWaterMl: Int = 2000,

    /** 偏好菜系（PostgreSQL TEXT[]），如川菜、粤菜、日料 */
    @TableField(typeHandler = PgStringArrayTypeHandler::class)
    val preferredCuisine: List<String> = emptyList(),

    /** 创建时间 */
    val createdAt: OffsetDateTime = OffsetDateTime.now(),

    /** 更新时间，由数据库触发器自动维护 */
    val updatedAt: OffsetDateTime = OffsetDateTime.now()
)
