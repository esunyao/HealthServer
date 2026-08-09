package cn.esuny.orion.service

import cn.esuny.orion.identity.AuthenticatedUser
import cn.esuny.orion.model.dto.user.UserProfileUpdateRequest
import cn.esuny.orion.model.vo.user.UserProfileVO
import cn.esuny.orion.model.vo.user.UserVO

interface UserService {
    fun getSelf(user: AuthenticatedUser): UserVO
    fun getProfile(user: AuthenticatedUser): UserProfileVO
    fun updateProfile(user: AuthenticatedUser, request: UserProfileUpdateRequest): UserProfileVO
    fun deactivate(user: AuthenticatedUser)
}
