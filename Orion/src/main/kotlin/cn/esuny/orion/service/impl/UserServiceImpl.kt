package cn.esuny.orion.service.impl

import cn.esuny.orion.handler.BusinessException
import cn.esuny.orion.identity.AuthenticatedUser
import cn.esuny.orion.mapper.UserMapper
import cn.esuny.orion.mapper.UserProfileMapper
import cn.esuny.orion.model.dto.user.UserProfileUpdateRequest
import cn.esuny.orion.model.entity.user.User
import cn.esuny.orion.model.entity.user.UserProfile
import cn.esuny.orion.model.vo.user.UserProfileVO
import cn.esuny.orion.model.vo.user.UserVO
import cn.esuny.orion.service.UserService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.LocalDate
import java.time.OffsetDateTime

@Service
class UserServiceImpl(
    private val userMapper: UserMapper,
    private val userProfileMapper: UserProfileMapper
) : UserService {

    override fun getSelf(user: AuthenticatedUser): UserVO {
        userMapper.touchLastSeen(user.userId, OffsetDateTime.now())
        return requireUser(user.userId).toVO()
    }

    override fun getProfile(user: AuthenticatedUser): UserProfileVO = requireProfile(user.userId).toVO()

    @Transactional
    override fun updateProfile(user: AuthenticatedUser, request: UserProfileUpdateRequest): UserProfileVO {
        val profile = requireProfile(user.userId)
        val birthDate = request.birthDate ?: profile.birthDate
        birthDate?.let(::validateBirthDate)
        val updated = profile.copy(
            birthDate = birthDate,
            gender = request.gender ?: profile.gender,
            heightCm = request.heightCm ?: profile.heightCm,
            activityLevel = request.activityLevel ?: profile.activityLevel,
            dailyWaterTargetMl = request.dailyWaterTargetMl ?: profile.dailyWaterTargetMl,
            profileCompletedAt = profile.profileCompletedAt ?: completedAt(birthDate, request.gender ?: profile.gender, request.heightCm ?: profile.heightCm, request.activityLevel ?: profile.activityLevel)
        )
        userProfileMapper.updateById(updated)
        return updated.toVO()
    }

    override fun deactivate(user: AuthenticatedUser) {
        if (userMapper.deactivate(user.userId) == 0) {
            throw BusinessException(409, "业务账户已注销", HttpStatus.CONFLICT)
        }
    }

    private fun requireUser(userId: java.util.UUID): User = userMapper.selectById(userId)
        ?: throw BusinessException(404, "用户不存在", HttpStatus.NOT_FOUND)

    private fun requireProfile(userId: java.util.UUID): UserProfile = userProfileMapper.selectByUserId(userId)
        ?: throw BusinessException(404, "用户档案不存在", HttpStatus.NOT_FOUND)

    private fun validateBirthDate(birthDate: LocalDate) {
        val years = java.time.Period.between(birthDate, LocalDate.now()).years
        if (years !in 10..120) throw BusinessException(400, "出生日期对应年龄必须在 10 至 120 岁之间")
    }

    private fun completedAt(
        birthDate: LocalDate?,
        gender: cn.esuny.orion.model.enums.user.Gender?,
        heightCm: java.math.BigDecimal?,
        activityLevel: cn.esuny.orion.model.enums.user.ActivityLevel?
    ): OffsetDateTime? = if (birthDate != null && gender != null && heightCm != null && activityLevel != null) OffsetDateTime.now() else null

    private fun User.toVO() = UserVO(
        userId, username, email, emailVerified, displayName,
        if (avatarObjectKey == null) null else "/v1/files/avatar",
        businessStatus, locale, timezone, lastSeenAt, createdAt, updatedAt
    )

    private fun UserProfile.toVO() = UserProfileVO(
        userId, birthDate, gender, heightCm, activityLevel, dailyWaterTargetMl,
        profileCompletedAt, createdAt, updatedAt
    )
}
