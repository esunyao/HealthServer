package cn.esuny.orion.mapper

import cn.esuny.orion.model.entity.user.User
import com.baomidou.mybatisplus.core.mapper.BaseMapper
import org.apache.ibatis.annotations.Insert
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.apache.ibatis.annotations.Select
import org.apache.ibatis.annotations.Update
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface UserMapper : BaseMapper<User> {
    @Insert(
        "INSERT INTO orion.users (user_id,username,email,email_verified,display_name,identity_synced_at) VALUES " +
            "(#{userId,typeHandler=cn.esuny.orion.model.typehandler.PgUuidTypeHandler},#{username},#{email},#{emailVerified},#{displayName},NOW()) " +
            "ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username,email=EXCLUDED.email," +
            "email_verified=EXCLUDED.email_verified,display_name=EXCLUDED.display_name,identity_synced_at=NOW() " +
            "WHERE orion.users.username IS DISTINCT FROM EXCLUDED.username " +
            "OR orion.users.email IS DISTINCT FROM EXCLUDED.email " +
            "OR orion.users.email_verified IS DISTINCT FROM EXCLUDED.email_verified " +
            "OR orion.users.display_name IS DISTINCT FROM EXCLUDED.display_name"
    )
    fun upsertIdentity(user: User): Int

    @Insert("INSERT INTO orion.user_profiles (user_id) VALUES (#{userId,typeHandler=cn.esuny.orion.model.typehandler.PgUuidTypeHandler}) ON CONFLICT (user_id) DO NOTHING")
    fun ensureProfile(@Param("userId") userId: UUID): Int

    @Select("SELECT * FROM orion.users WHERE user_id = #{userId,typeHandler=cn.esuny.orion.model.typehandler.PgUuidTypeHandler} FOR UPDATE")
    fun selectByIdForUpdate(@Param("userId") userId: UUID): User?

    @Update("UPDATE orion.users SET last_seen_at=#{lastSeenAt} WHERE user_id=#{userId,typeHandler=cn.esuny.orion.model.typehandler.PgUuidTypeHandler}")
    fun touchLastSeen(@Param("userId") userId: UUID, @Param("lastSeenAt") lastSeenAt: OffsetDateTime): Int

    @Update("UPDATE orion.users SET business_status='deactivated',deleted_at=NOW() WHERE user_id=#{userId,typeHandler=cn.esuny.orion.model.typehandler.PgUuidTypeHandler} AND business_status <> 'deactivated'")
    fun deactivate(@Param("userId") userId: UUID): Int

    @Select("<script>SELECT avatar_object_key FROM orion.users " +
        "WHERE avatar_object_key IN <foreach collection='keys' item='key' open='(' separator=',' close=')'>#{key}</foreach></script>")
    fun selectReferencedAvatarKeys(@Param("keys") keys: Collection<String>): List<String>
}
