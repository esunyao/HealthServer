package cn.esuny.orion.service

import cn.esuny.orion.model.dto.auth.LoginRequest
import cn.esuny.orion.model.dto.auth.LoginResponse
import cn.esuny.orion.model.dto.auth.RefreshRequest
import cn.esuny.orion.model.dto.auth.RegisterRequest

/**
 * 认证业务接口
 */
interface AuthService {

    /**
     * 用户注册
     */
    fun register(request: RegisterRequest)

    /**
     * 用户登录，返回 access + refresh token
     */
    fun login(request: LoginRequest): LoginResponse

    /**
     * 用 refresh token 换取新的 access token
     */
    fun refresh(request: RefreshRequest): LoginResponse

    /**
     * 登出，废除 refresh token
     */
    fun logout(refreshToken: String)
}
