package cn.esuny.orion.model.entity.user

import com.baomidou.mybatisplus.annotation.IdType
import com.baomidou.mybatisplus.annotation.TableId
import com.baomidou.mybatisplus.annotation.TableName
import java.time.OffsetDateTime
import java.util.UUID

/** Authentik 身份在 Orion 的业务缓存，不保存凭证或令牌。 */
@TableName("orion.users")
data class User(
    @TableId(type = IdType.INPUT)
    val userId: UUID,
    val username: String,
    val email: String? = null,
    val emailVerified: Boolean = false,
    val displayName: String = "",
    val avatarObjectKey: String? = null,
    val businessStatus: BusinessStatus = BusinessStatus.active,
    val locale: String = "zh-CN",
    val timezone: String = "Asia/Shanghai",
    val lastSeenAt: OffsetDateTime? = null,
    val identitySyncedAt: OffsetDateTime = OffsetDateTime.now(),
    val createdAt: OffsetDateTime = OffsetDateTime.now(),
    val updatedAt: OffsetDateTime = OffsetDateTime.now(),
    val deletedAt: OffsetDateTime? = null
)
