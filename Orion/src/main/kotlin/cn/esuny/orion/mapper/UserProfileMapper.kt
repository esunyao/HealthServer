package cn.esuny.orion.mapper

import cn.esuny.orion.model.entity.user.UserProfile
import com.baomidou.mybatisplus.core.mapper.BaseMapper
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Select

@Mapper
interface UserProfileMapper : BaseMapper<UserProfile> {

    @Select("SELECT * FROM user_profiles WHERE user_id = #{userId}")
    fun selectByUserId(userId: java.util.UUID): UserProfile?
}
