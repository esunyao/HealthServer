package cn.esuny.orion.mapper

import cn.esuny.orion.model.entity.user.User
import com.baomidou.mybatisplus.core.mapper.BaseMapper
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.apache.ibatis.annotations.Select

@Mapper
interface UserMapper : BaseMapper<User> {
    @Select("SELECT * FROM \"User\".users WHERE username = #{username}")
    fun selectByUsername(username: String): User?

    @Select("SELECT * FROM \"User\".users WHERE email = #{email}")
    fun selectByEmail(email: String): User?

    @Select("SELECT * FROM \"User\".users WHERE user_id = #{userId} FOR UPDATE")
    fun selectByIdForUpdate(@Param("userId") userId: Long): User?

    @Select("<script>SELECT avatar_url FROM \"User\".users " +
            "WHERE avatar_url IN <foreach collection='keys' item='key' open='(' separator=',' close=')'>#{key}</foreach></script>")
    fun selectReferencedAvatarKeys(@Param("keys") keys: Collection<String>): List<String>
}
