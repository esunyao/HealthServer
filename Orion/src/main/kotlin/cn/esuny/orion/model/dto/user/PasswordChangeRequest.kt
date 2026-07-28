package cn.esuny.orion.model.dto.user

import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.Size

/**
 * 修改密码请求体
 */
data class PasswordChangeRequest(
    @field:NotBlank(message = "旧密码不能为空")
    val oldPassword: String = "",

    @field:NotBlank(message = "新密码不能为空")
    @field:Size(min = 6, max = 100, message = "密码长度 6-100 个字符")
    val newPassword: String = ""
)
