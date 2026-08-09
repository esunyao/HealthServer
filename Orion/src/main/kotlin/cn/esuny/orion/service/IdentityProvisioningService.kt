package cn.esuny.orion.service

import cn.esuny.orion.handler.BusinessException
import cn.esuny.orion.identity.AuthenticatedUser
import cn.esuny.orion.mapper.UserMapper
import cn.esuny.orion.model.entity.user.BusinessStatus
import cn.esuny.orion.model.entity.user.User
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime

@Service
class IdentityProvisioningService(
    private val userMapper: UserMapper
) {
    @Transactional
    fun provision(identity: AuthenticatedUser): User {
        if (!identity.emailVerified) {
            throw BusinessException(403, "请先完成邮箱验证", HttpStatus.FORBIDDEN)
        }
        try {
            userMapper.upsertIdentity(
                User(
                    userId = identity.userId,
                    username = identity.username,
                    email = identity.email,
                    emailVerified = true,
                    displayName = identity.displayName
                )
            )
        } catch (_: DataIntegrityViolationException) {
            throw BusinessException(409, "用户名或邮箱已关联其他业务用户", HttpStatus.CONFLICT)
        }
        userMapper.ensureProfile(identity.userId)
        val user = userMapper.selectById(identity.userId)
            ?: throw BusinessException(500, "用户自动建档失败", HttpStatus.INTERNAL_SERVER_ERROR)
        if (user.businessStatus != BusinessStatus.active || user.deletedAt != null) {
            throw BusinessException(403, "业务账户不可用", HttpStatus.FORBIDDEN)
        }
        return user
    }
}
