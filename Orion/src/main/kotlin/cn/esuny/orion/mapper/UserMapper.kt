package cn.esuny.orion.mapper

import cn.esuny.orion.model.entity.user.User
import com.baomidou.mybatisplus.core.mapper.BaseMapper
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Select

@Mapper
interface UserMapper : BaseMapper<User> {

    @Select("SELECT * FROM users WHERE username = #{username}")
    fun selectByUsername(username: String): User?

    @Select("SELECT * FROM users WHERE email = #{email}")
    fun selectByEmail(email: String): User?
}
