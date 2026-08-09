package cn.esuny.orion.model.vo.user

import cn.esuny.orion.model.entity.user.BusinessStatus
import java.time.OffsetDateTime
import java.util.UUID

data class UserVO(
    val userId: UUID,
    val username: String,
    val email: String?,
    val emailVerified: Boolean,
    val displayName: String,
    val avatarUrl: String?,
    val businessStatus: BusinessStatus,
    val locale: String,
    val timezone: String,
    val lastSeenAt: OffsetDateTime?,
    val createdAt: OffsetDateTime,
    val updatedAt: OffsetDateTime
)
