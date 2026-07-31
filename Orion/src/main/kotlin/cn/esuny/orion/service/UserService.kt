package cn.esuny.orion.service

import cn.esuny.orion.model.dto.user.PasswordChangeRequest
import cn.esuny.orion.model.dto.user.UserProfileUpdateRequest
import cn.esuny.orion.model.dto.user.UserUpdateRequest
import cn.esuny.orion.model.vo.user.UserProfileVO
import cn.esuny.orion.model.vo.user.UserVO

/**
 * 用户信息业务接口
 */
interface UserService {

    /**
     * 获取当前用户信息
     */
    fun getSelf(userId: Long): UserVO

    /**
     * 更新当前用户基础信息（昵称、头像）
     */
    fun updateSelf(userId: Long, request: UserUpdateRequest): UserVO

    /**
     * 修改密码
     */
    fun changePassword(userId: Long, request: PasswordChangeRequest)

    /**
     * 获取用户画像
     */
    fun getProfile(userId: Long): UserProfileVO

    /**
     * 更新用户画像
     */
    fun updateProfile(userId: Long, request: UserProfileUpdateRequest): UserProfileVO
}
