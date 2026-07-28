package cn.esuny.orion.model.dto.auth

import jakarta.validation.constraints.Email
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.Size

/**
 * 用户注册请求体
 */
data class RegisterRequest(
    @field:NotBlank(message = "用户名不能为空")
    @field:Size(min = 2, max = 50, message = "用户名长度 2-50 个字符")
    val username: String = "",

    @field:NotBlank(message = "邮箱不能为空")
    @field:Email(message = "邮箱格式不正确")
    val email: String = "",

    @field:NotBlank(message = "密码不能为空")
    @field:Size(min = 6, max = 100, message = "密码长度 6-100 个字符")
    val password: String = "",

    /** 昵称，可选，默认与用户名相同 */
    val nickname: String = ""
)
