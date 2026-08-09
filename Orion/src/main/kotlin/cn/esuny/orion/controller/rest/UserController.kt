package cn.esuny.orion.controller.rest

import cn.esuny.orion.identity.AuthenticatedUser
import cn.esuny.orion.identity.CurrentUser
import cn.esuny.orion.model.dto.user.UserProfileUpdateRequest
import cn.esuny.orion.model.result.ApiResponse
import cn.esuny.orion.model.vo.user.UserProfileVO
import cn.esuny.orion.model.vo.user.UserVO
import cn.esuny.orion.service.UserService
import jakarta.validation.Valid
import org.springframework.web.bind.annotation.DeleteMapping
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PatchMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/v1/users/self")
class UserController(private val userService: UserService) {

    @GetMapping
    fun getSelf(@CurrentUser user: AuthenticatedUser): ApiResponse<UserVO> =
        ApiResponse.success(data = userService.getSelf(user))

    @DeleteMapping
    fun deactivate(@CurrentUser user: AuthenticatedUser): ApiResponse<Unit> {
        userService.deactivate(user)
        return ApiResponse.success(message = "业务账户已注销")
    }

    @GetMapping("/profile")
    fun getProfile(@CurrentUser user: AuthenticatedUser): ApiResponse<UserProfileVO> =
        ApiResponse.success(data = userService.getProfile(user))

    @PatchMapping("/profile")
    fun updateProfile(
        @CurrentUser user: AuthenticatedUser,
        @RequestBody @Valid request: UserProfileUpdateRequest
    ): ApiResponse<UserProfileVO> = ApiResponse.success(data = userService.updateProfile(user, request), message = "档案更新成功")
}
