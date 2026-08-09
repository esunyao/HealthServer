package cn.esuny.orion.mapper

import cn.esuny.orion.model.entity.user.UserProfile
import com.baomidou.mybatisplus.core.mapper.BaseMapper
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Select
import java.util.UUID

@Mapper
interface UserProfileMapper : BaseMapper<UserProfile> {
    @Select("SELECT * FROM orion.user_profiles WHERE user_id = #{userId,typeHandler=cn.esuny.orion.model.typehandler.PgUuidTypeHandler}")
    fun selectByUserId(userId: UUID): UserProfile?
}
