package cn.esuny.orion.controller.rest

import cn.esuny.orion.model.result.ApiResponse
import cn.esuny.orion.model.dto.user.PasswordChangeRequest
import cn.esuny.orion.model.dto.user.UserProfileUpdateRequest
import cn.esuny.orion.model.dto.user.UserUpdateRequest
import cn.esuny.orion.model.vo.user.UserProfileVO
import cn.esuny.orion.model.vo.user.UserVO
import cn.esuny.orion.service.UserService
import jakarta.validation.Valid
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestHeader
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

/**
 * 用户信息控制器
 *
 * 处理当前用户的信息查询与更新。
 * 用户 ID 由 Gateway 认证后通过 X-User-Id 请求头传入。
 * 通过 Gateway 路由：/api/user/v1/users/... → StripPrefix=2 → /v1/users/...
 */
@RestController
@RequestMapping("/v1/users")
class UserController(private val userService: UserService) {

    /**
     * 获取当前用户信息
     *
     * GET /v1/users/self
     */
    @GetMapping("/self")
    fun getSelf(@RequestHeader("X-User-Id") userId: UUID): ApiResponse<UserVO> {
        val user = userService.getSelf(userId)
        return ApiResponse.success(data = user)
    }

    /**
     * 更新当前用户基础信息
     *
     * PUT /v1/users/self
     */
    @PutMapping("/self")
    fun updateSelf(@RequestHeader("X-User-Id") userId: UUID, @RequestBody @Valid request: UserUpdateRequest): ApiResponse<UserVO> {
        val user = userService.updateSelf(userId, request)
        return ApiResponse.success(data = user, message = "更新成功")
    }

    /**
     * 修改密码
     *
     * PUT /v1/users/self/password
     */
    @PutMapping("/self/password")
    fun changePassword(@RequestHeader("X-User-Id") userId: UUID, @RequestBody @Valid request: PasswordChangeRequest): ApiResponse<Unit> {
        userService.changePassword(userId, request)
        return ApiResponse.success(message = "密码修改成功")
    }

    /**
     * 获取用户画像
     *
     * GET /v1/users/self/profile
     */
    @GetMapping("/self/profile")
    fun getProfile(@RequestHeader("X-User-Id") userId: UUID): ApiResponse<UserProfileVO> {
        val profile = userService.getProfile(userId)
        return ApiResponse.success(data = profile)
    }

    /**
     * 更新用户画像
     *
     * PUT /v1/users/self/profile
     */
    @PutMapping("/self/profile")
    fun updateProfile(@RequestHeader("X-User-Id") userId: UUID, @RequestBody @Valid request: UserProfileUpdateRequest): ApiResponse<UserProfileVO> {
        val profile = userService.updateProfile(userId, request)
        return ApiResponse.success(data = profile, message = "画像更新成功")
    }
}
