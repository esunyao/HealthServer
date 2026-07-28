package cn.esuny.orion.controller.rest

import cn.esuny.orion.model.result.ApiResponse
import cn.esuny.orion.model.dto.auth.LoginRequest
import cn.esuny.orion.model.dto.auth.LoginResponse
import cn.esuny.orion.model.dto.auth.RefreshRequest
import cn.esuny.orion.model.dto.auth.RegisterRequest
import cn.esuny.orion.service.AuthService
import jakarta.validation.Valid
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

/**
 * 认证控制器
 *
 * 处理用户注册、登录、Token 刷新、登出。
 * 通过 Gateway 路由：/api/user/v1/auth/... → StripPrefix=2 → /v1/auth/...
 */
@RestController
@RequestMapping("/v1/auth")
class AuthController(private val authService: AuthService) {

    /**
     * 用户注册
     *
     * POST /v1/auth/register
     */
    @PostMapping("/register")
    fun register(@RequestBody @Valid request: RegisterRequest): ApiResponse<Unit> {
        authService.register(request)
        return ApiResponse.success(message = "注册成功")
    }

    /**
     * 用户登录
     *
     * POST /v1/auth/login
     * 返回 accessToken + refreshToken
     */
    @PostMapping("/login")
    fun login(@RequestBody @Valid request: LoginRequest): ApiResponse<LoginResponse> {
        val response = authService.login(request)
        return ApiResponse.success(data = response, message = "登录成功")
    }

    /**
     * 刷新 Token
     *
     * POST /v1/auth/refresh
     * 用 refreshToken 换取新的 accessToken
     */
    @PostMapping("/refresh")
    fun refresh(@RequestBody @Valid request: RefreshRequest): ApiResponse<LoginResponse> {
        val response = authService.refresh(request)
        return ApiResponse.success(data = response)
    }

    /**
     * 用户登出
     *
     * POST /v1/auth/logout
     * 废除 refreshToken，使其失效
     */
    @PostMapping("/logout")
    fun logout(@RequestBody request: RefreshRequest): ApiResponse<Unit> {
        authService.logout(request.refreshToken)
        return ApiResponse.success(message = "登出成功")
    }
}
