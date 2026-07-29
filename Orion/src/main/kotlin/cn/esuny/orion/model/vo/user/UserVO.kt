package cn.esuny.orion.model.vo.user

import cn.esuny.orion.model.enums.user.UserStatus
import java.time.OffsetDateTime
import java.util.UUID

/**
 * 用户信息视图对象（返回给客户端）
 */
data class UserVO(
    // 使用String，防止精度丢失
    val userId: String,
    val username: String,
    val email: String,
    val nickname: String,
    val avatarUrl: String,
    val status: UserStatus,
    val createdAt: OffsetDateTime,
    val updatedAt: OffsetDateTime
)
