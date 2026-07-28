package cn.esuny.orion.util

import io.jsonwebtoken.Claims
import io.jsonwebtoken.Jwts
import io.jsonwebtoken.security.Keys
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import java.util.Date
import javax.crypto.SecretKey

/**
 * JWT 工具类
 *
 * 负责 Access Token 和 Refresh Token 的生成与解析。
 * 密钥从 application.yaml 中的 `jwt.secret` 配置读取。
 */
@Component
class JwtUtil {

    @Value("\${jwt.secret}")
    private lateinit var secret: String

    @Value("\${jwt.access-token-expiration}")
    private var accessTokenExpiration: Long = 900_000 // 15 分钟

    @Value("\${jwt.refresh-token-expiration}")
    private var refreshTokenExpiration: Long = 604_800_000 // 7 天

    private val key: SecretKey by lazy {
        Keys.hmacShaKeyFor(secret.toByteArray())
    }

    /**
     * 生成 Access Token
     */
    fun generateAccessToken(userId: String, username: String): String {
        return Jwts.builder()
            .subject(userId)
            .claim("username", username)
            .issuedAt(Date())
            .expiration(Date(System.currentTimeMillis() + accessTokenExpiration))
            .signWith(key)
            .compact()
    }

    /**
     * 生成 Refresh Token
     */
    fun generateRefreshToken(userId: String, username: String): String {
        return Jwts.builder()
            .subject(userId)
            .claim("username", username)
            .issuedAt(Date())
            .expiration(Date(System.currentTimeMillis() + refreshTokenExpiration))
            .signWith(key)
            .compact()
    }

    /**
     * 解析 Token，返回 Claims
     */
    fun parseToken(token: String): Claims {
        return Jwts.parser()
            .verifyWith(key)
            .build()
            .parseSignedClaims(token)
            .payload
    }

    /**
     * 从 Token 中获取用户 ID
     */
    fun getUserId(token: String): String {
        return parseToken(token).subject
    }

    /**
     * 从 Token 中获取用户名
     */
    fun getUsername(token: String): String {
        return parseToken(token)["username"] as String
    }

    /**
     * 校验 Token 是否有效（未过期）
     */
    fun validateToken(token: String): Boolean {
        return try {
            val claims = parseToken(token)
            claims.expiration.after(Date())
        } catch (e: Exception) {
            false
        }
    }

    /**
     * 获取 Access Token 过期时间（毫秒）
     */
    fun getAccessTokenExpiration(): Long = accessTokenExpiration

    /**
     * 获取 Refresh Token 过期时间（秒），用于 Redis TTL
     */
    fun getRefreshTokenExpirationSeconds(): Long = refreshTokenExpiration / 1000
}
