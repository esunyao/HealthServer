package cn.esuny.orion.model.entity.user

import cn.esuny.orion.model.enums.user.UserStatus
import com.baomidou.mybatisplus.annotation.IdType
import com.baomidou.mybatisplus.annotation.TableField
import com.baomidou.mybatisplus.annotation.TableId
import com.baomidou.mybatisplus.annotation.TableName
import java.time.OffsetDateTime
import java.util.UUID

/**
 * 用户基础账户信息
 *
 * 存储登录凭证、昵称、头像、账户状态等，
 * 是其他所有业务表的关联核心。
 */
@TableName("\"User\".users")
data class User(
    /** 用户唯一标识，时间有序 UUID */
    @TableId(type = IdType.ASSIGN_ID)
    var userId: Long? = null,

    /** 登录用户名，全局唯一 */
    val username: String = "",

    /** 邮箱地址，用于登录和通知 */
    val email: String = "",

    /** 密码哈希值（bcrypt），禁止明文存储 */
    val passwordHash: String = "",

    /** 用户昵称 */
    val nickname: String = "",

    /** 头像 URL 地址 */
    val avatarUrl: String = "",

    /** 账户状态：active / disabled / deleted */
    @TableField("status")
    val status: UserStatus = UserStatus.active,

    /** 最后登录时间 */
    val lastLoginAt: OffsetDateTime? = null,

    /** 注册时间 */
    val createdAt: OffsetDateTime = OffsetDateTime.now(),

    /** 资料更新时间，由数据库触发器自动维护 */
    val updatedAt: OffsetDateTime = OffsetDateTime.now()
)
