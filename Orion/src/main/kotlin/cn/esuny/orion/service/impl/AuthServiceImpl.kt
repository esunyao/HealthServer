package cn.esuny.orion.service.impl

import cn.esuny.orion.handler.BusinessException
import cn.esuny.orion.mapper.UserMapper
import cn.esuny.orion.mapper.UserProfileMapper
import cn.esuny.orion.model.dto.auth.LoginRequest
import cn.esuny.orion.model.dto.auth.LoginResponse
import cn.esuny.orion.model.dto.auth.RefreshRequest
import cn.esuny.orion.model.dto.auth.RegisterRequest
import cn.esuny.orion.model.entity.user.User
import cn.esuny.orion.model.entity.user.UserProfile
import cn.esuny.orion.model.enums.user.UserStatus
import cn.esuny.orion.service.AuthService
import cn.esuny.orion.util.JwtUtil
import org.slf4j.LoggerFactory
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * 认证业务实现
 */
@Service
class AuthServiceImpl(
    private val userMapper: UserMapper,
    private val userProfileMapper: UserProfileMapper,
    private val jwtUtil: JwtUtil,
    private val redisTemplate: StringRedisTemplate
) : AuthService {

    private val log = LoggerFactory.getLogger(AuthServiceImpl::class.java)
    private val passwordEncoder = BCryptPasswordEncoder()

    companion object {
        private const val REFRESH_TOKEN_PREFIX = "auth:refresh:"
    }

    @Transactional
    override fun register(request: RegisterRequest) {
        // 校验用户名唯一
        userMapper.selectByUsername(request.username)?.let {
            throw BusinessException(400, "用户名已被注册")
        }

        // 校验邮箱唯一
        userMapper.selectByEmail(request.email)?.let {
            throw BusinessException(400, "邮箱已被注册")
        }

        val userId = UUID.randomUUID()
        val now = OffsetDateTime.now()

        // 创建用户
        val user = User(
            userId = userId,
            username = request.username,
            email = request.email,
            passwordHash = passwordEncoder.encode(request.password)!!,
            nickname = request.nickname.ifBlank { request.username },
            status = UserStatus.active,
            createdAt = now,
            updatedAt = now
        )
        userMapper.insert(user)

        // 创建用户画像（1:1 关系）
        val profile = UserProfile(
            userId = userId,
            createdAt = now,
            updatedAt = now
        )
        userProfileMapper.insert(profile)

        log.info("用户注册成功: username={}, userId={}", request.username, userId)
    }

    override fun login(request: LoginRequest): LoginResponse {
        val user = userMapper.selectByUsername(request.username)
            ?: throw BusinessException(401, "用户名或密码错误", org.springframework.http.HttpStatus.UNAUTHORIZED)

        if (!passwordEncoder.matches(request.password, user.passwordHash)) {
            throw BusinessException(401, "用户名或密码错误", org.springframework.http.HttpStatus.UNAUTHORIZED)
        }

        if (user.status != UserStatus.active) {
            throw BusinessException(403, "账户已被禁用", org.springframework.http.HttpStatus.FORBIDDEN)
        }

        val userId = user.userId!!.toString()
        val username = user.username

        // 生成 Token
        val accessToken = jwtUtil.generateAccessToken(userId, username)
        val refreshToken = jwtUtil.generateRefreshToken(userId, username)

        // Refresh Token 存入 Redis
        val redisKey = "$REFRESH_TOKEN_PREFIX$userId"
        redisTemplate.opsForValue().set(redisKey, refreshToken, jwtUtil.getRefreshTokenExpirationSeconds(), TimeUnit.SECONDS)

        // 更新最后登录时间
        userMapper.updateById(user.copy(lastLoginAt = OffsetDateTime.now()))

        log.info("用户登录成功: username={}", username)

        return LoginResponse(
            accessToken = accessToken,
            refreshToken = refreshToken,
            expiresIn = jwtUtil.getAccessTokenExpiration()
        )
    }

    override fun refresh(request: RefreshRequest): LoginResponse {
        // 校验 refreshToken 有效性
        if (!jwtUtil.validateToken(request.refreshToken)) {
            throw BusinessException(401, "refreshToken 无效或已过期", org.springframework.http.HttpStatus.UNAUTHORIZED)
        }

        val userId = jwtUtil.getUserId(request.refreshToken)
        val username = jwtUtil.getUsername(request.refreshToken)

        // 校验 Redis 中是否存在
        val redisKey = "$REFRESH_TOKEN_PREFIX$userId"
        val storedToken = redisTemplate.opsForValue().get(redisKey)
        if (storedToken != request.refreshToken) {
            throw BusinessException(401, "refreshToken 已失效", org.springframework.http.HttpStatus.UNAUTHORIZED)
        }

        // 生成新的 Token 对
        val newAccessToken = jwtUtil.generateAccessToken(userId, username)
        val newRefreshToken = jwtUtil.generateRefreshToken(userId, username)

        // 替换 Redis 中的 refreshToken
        redisTemplate.opsForValue().set(redisKey, newRefreshToken, jwtUtil.getRefreshTokenExpirationSeconds(), TimeUnit.SECONDS)

        return LoginResponse(
            accessToken = newAccessToken,
            refreshToken = newRefreshToken,
            expiresIn = jwtUtil.getAccessTokenExpiration()
        )
    }

    override fun logout(refreshToken: String) {
        try {
            val userId = jwtUtil.getUserId(refreshToken)
            val redisKey = "$REFRESH_TOKEN_PREFIX$userId"
            redisTemplate.delete(redisKey)
            log.info("用户登出成功: userId={}", userId)
        } catch (e: Exception) {
            log.warn("登出时解析 refreshToken 失败: {}", e.message)
        }
    }
}
