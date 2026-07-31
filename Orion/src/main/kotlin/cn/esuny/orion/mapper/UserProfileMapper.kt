package cn.esuny.orion.mapper

import cn.esuny.orion.model.entity.user.UserProfile
import cn.esuny.orion.model.enums.user.ActivityLevel
import cn.esuny.orion.model.enums.user.Gender
import cn.esuny.orion.model.enums.user.HealthGoal
import cn.esuny.orion.model.typehandler.OffsetDateTimeTypeHandler
import cn.esuny.orion.model.typehandler.PgStringArrayTypeHandler
import com.baomidou.mybatisplus.core.mapper.BaseMapper
import org.apache.ibatis.annotations.Arg
import org.apache.ibatis.annotations.ConstructorArgs
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Select
import org.apache.ibatis.type.EnumTypeHandler
import java.math.BigDecimal
import java.time.OffsetDateTime

@Mapper
interface UserProfileMapper : BaseMapper<UserProfile> {

    /**
     * 根据用户ID查询用户画像
     *
     * 使用 @ConstructorArgs 显式定义构造函数参数映射，解决 Kotlin 数据类与 JDBC 类型不匹配问题：
     * - 枚举字段：Gender, ActivityLevel, HealthGoal → 使用 EnumTypeHandler
     * - 数组字段：allergies, dietaryRestrictions, medicalConditions, preferredCuisine → 使用 PgStringArrayTypeHandler
     * - 时间字段：createdAt, updatedAt → 使用 OffsetDateTimeTypeHandler
     *
     * 注意：@Arg 不需要 property 属性，MyBatis 根据 column 名通过 map-underscore-to-camel-case 策略推断属性名
     */
    @Select("SELECT * FROM \"User\".user_profiles WHERE user_id = #{userId}")
    @ConstructorArgs(
        Arg(column = "profile_id", javaType = java.lang.Long::class),
        Arg(column = "user_id", javaType = Long::class),
        Arg(column = "age", javaType = java.lang.Integer::class),
        Arg(column = "gender", javaType = Gender::class, typeHandler = EnumTypeHandler::class),
        Arg(column = "height_cm", javaType = BigDecimal::class),
        Arg(column = "weight_kg", javaType = BigDecimal::class),
        Arg(column = "bmi", javaType = BigDecimal::class),
        Arg(column = "activity_level", javaType = ActivityLevel::class, typeHandler = EnumTypeHandler::class),
        Arg(column = "health_goal", javaType = HealthGoal::class, typeHandler = EnumTypeHandler::class),
        Arg(column = "allergies", javaType = List::class, typeHandler = PgStringArrayTypeHandler::class),
        Arg(column = "dietary_restrictions", javaType = List::class, typeHandler = PgStringArrayTypeHandler::class),
        Arg(column = "medical_conditions", javaType = List::class, typeHandler = PgStringArrayTypeHandler::class),
        Arg(column = "daily_water_ml", javaType = Int::class),
        Arg(column = "preferred_cuisine", javaType = List::class, typeHandler = PgStringArrayTypeHandler::class),
        Arg(column = "created_at", javaType = OffsetDateTime::class, typeHandler = OffsetDateTimeTypeHandler::class),
        Arg(column = "updated_at", javaType = OffsetDateTime::class, typeHandler = OffsetDateTimeTypeHandler::class)
    )
    fun selectByUserId(userId: Long): UserProfile?
}
