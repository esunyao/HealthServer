package cn.esuny.orion.service.impl

import cn.esuny.orion.handler.BusinessException
import cn.esuny.orion.mapper.UserMapper
import cn.esuny.orion.mapper.UserProfileMapper
import cn.esuny.orion.model.dto.user.PasswordChangeRequest
import cn.esuny.orion.model.dto.user.UserProfileUpdateRequest
import cn.esuny.orion.model.dto.user.UserUpdateRequest
import cn.esuny.orion.model.entity.user.UserProfile
import cn.esuny.orion.model.vo.user.UserProfileVO
import cn.esuny.orion.model.vo.user.UserVO
import cn.esuny.orion.service.UserService
import org.slf4j.LoggerFactory
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder
import org.springframework.stereotype.Service
import java.time.OffsetDateTime

/**
 * 用户信息业务实现
 */
@Service
class UserServiceImpl(
    private val userMapper: UserMapper,
    private val userProfileMapper: UserProfileMapper
) : UserService {

    private val log = LoggerFactory.getLogger(UserServiceImpl::class.java)
    private val passwordEncoder = BCryptPasswordEncoder()

    override fun getSelf(userId: Long): UserVO {
        val user = userMapper.selectById(userId)
            ?: throw BusinessException(404, "用户不存在", org.springframework.http.HttpStatus.NOT_FOUND)
        return user.toVO()
    }

    override fun updateSelf(userId: Long, request: UserUpdateRequest): UserVO {
        if (request.avatarUrl != null) {
            throw BusinessException(400, "头像只能通过文件上传确认接口更新", org.springframework.http.HttpStatus.BAD_REQUEST)
        }

        val user = userMapper.selectById(userId)
            ?: throw BusinessException(404, "用户不存在", org.springframework.http.HttpStatus.NOT_FOUND)

        val updated = user.copy(
            nickname = request.nickname ?: user.nickname,
            updatedAt = OffsetDateTime.now()
        )
        userMapper.updateById(updated)
        return updated.toVO()
    }

    override fun changePassword(userId: Long, request: PasswordChangeRequest) {
        val user = userMapper.selectById(userId)
            ?: throw BusinessException(404, "用户不存在", org.springframework.http.HttpStatus.NOT_FOUND)

        if (!passwordEncoder.matches(request.oldPassword, user.passwordHash)) {
            throw BusinessException(400, "旧密码不正确")
        }

        val updated = user.copy(
            passwordHash = passwordEncoder.encode(request.newPassword)!!,
            updatedAt = OffsetDateTime.now()
        )
        userMapper.updateById(updated)
        log.info("用户修改密码成功: userId={}", userId)
    }

    override fun getProfile(userId: Long): UserProfileVO {
        val profile = userProfileMapper.selectByUserId(userId)
            ?: throw BusinessException(404, "用户画像不存在", org.springframework.http.HttpStatus.NOT_FOUND)
        return profile.toVO()
    }

    override fun updateProfile(userId: Long, request: UserProfileUpdateRequest): UserProfileVO {
        val profile = userProfileMapper.selectByUserId(userId)
            ?: throw BusinessException(404, "用户画像不存在", org.springframework.http.HttpStatus.NOT_FOUND)

        val updated = profile.copy(
            age = request.age ?: profile.age,
            gender = request.gender ?: profile.gender,
            heightCm = request.heightCm ?: profile.heightCm,
            weightKg = request.weightKg ?: profile.weightKg,
            activityLevel = request.activityLevel ?: profile.activityLevel,
            healthGoal = request.healthGoal ?: profile.healthGoal,
            allergies = request.allergies ?: profile.allergies,
            dietaryRestrictions = request.dietaryRestrictions ?: profile.dietaryRestrictions,
            medicalConditions = request.medicalConditions ?: profile.medicalConditions,
            dailyWaterMl = request.dailyWaterMl ?: profile.dailyWaterMl,
            preferredCuisine = request.preferredCuisine ?: profile.preferredCuisine,
            updatedAt = OffsetDateTime.now()
        )
        userProfileMapper.updateById(updated)
        return updated.toVO()
    }

    // ==================== Entity → VO 转换 ====================

    private fun cn.esuny.orion.model.entity.user.User.toVO() = UserVO(
        userId = userId.toString(),
        username = username,
        email = email,
        nickname = nickname,
        avatarUrl = avatarUrl,
        status = status,
        createdAt = createdAt,
        updatedAt = updatedAt
    )

    private fun UserProfile.toVO() = UserProfileVO(
        profileId = profileId.toString(),
        userId = userId.toString(),
        age = age,
        gender = gender,
        heightCm = heightCm,
        weightKg = weightKg,
        bmi = bmi,
        activityLevel = activityLevel,
        healthGoal = healthGoal,
        allergies = allergies,
        dietaryRestrictions = dietaryRestrictions,
        medicalConditions = medicalConditions,
        dailyWaterMl = dailyWaterMl,
        preferredCuisine = preferredCuisine,
        createdAt = createdAt,
        updatedAt = updatedAt
    )
}
