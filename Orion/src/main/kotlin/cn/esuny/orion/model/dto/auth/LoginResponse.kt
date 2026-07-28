package cn.esuny.orion.model.dto.auth

/**
 * 登录 / 刷新 Token 响应体
 */
data class LoginResponse(
    /** 访问令牌，有效期 15 分钟 */
    val accessToken: String,

    /** 刷新令牌，有效期 7 天 */
    val refreshToken: String,

    /** Access Token 过期时间（毫秒） */
    val expiresIn: Long
)
