package cn.esuny.orion.model.dto.auth

import jakarta.validation.constraints.NotBlank

/**
 * 用户登录请求体
 */
data class LoginRequest(
    @field:NotBlank(message = "用户名不能为空")
    val username: String = "",

    @field:NotBlank(message = "密码不能为空")
    val password: String = ""
)
