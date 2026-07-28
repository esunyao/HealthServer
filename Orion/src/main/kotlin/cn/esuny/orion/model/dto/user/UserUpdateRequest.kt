package cn.esuny.orion.model.dto.user

/**
 * 更新用户基础信息请求体
 */
data class UserUpdateRequest(
    /** 昵称 */
    val nickname: String? = null,

    /** 头像 URL */
    val avatarUrl: String? = null
)
