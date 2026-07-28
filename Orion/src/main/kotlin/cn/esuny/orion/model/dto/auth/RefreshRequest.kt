package cn.esuny.orion.model.dto.auth

import jakarta.validation.constraints.NotBlank

/**
 * 刷新 Token 请求体
 */
data class RefreshRequest(
    @field:NotBlank(message = "refreshToken 不能为空")
    val refreshToken: String = ""
)
