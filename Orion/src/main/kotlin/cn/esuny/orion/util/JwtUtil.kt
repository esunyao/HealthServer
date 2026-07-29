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

    companion object {
        const val ACCESS_TOKEN_TYPE = "access"
        const val REFRESH_TOKEN_TYPE = "refresh"
        private const val TOKEN_TYPE_CLAIM = "tokenType"
    }

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
            .subject(userId)                                                      // 1. 标准声明 (sub)：写入用户唯一ID
            .claim("username", username)                                           // 2. 自定义声明：写入用户名
            .claim(TOKEN_TYPE_CLAIM, ACCESS_TOKEN_TYPE)                             // 3. 令牌用途：仅用于 API 访问
            .issuedAt(Date())                                                     // 3. 标准声明 (iat)：签发时间 (Issued At)
            .expiration(Date(System.currentTimeMillis() + accessTokenExpiration)) // 4. 标准声明 (exp)：过期时间 (Expiration)
            .signWith(key)                                                        // 5. 秘钥签名：用防篡改密钥进行 HMAC 签名
            .compact()                                                            // 6. 压缩输出：拼装成 header.payload.signature 三段式字符串
    }

    /**
     * 生成 Refresh Token
     */
    fun generateRefreshToken(userId: String, username: String): String {
        return Jwts.builder()
            .subject(userId)
            .claim("username", username)
            .claim(TOKEN_TYPE_CLAIM, REFRESH_TOKEN_TYPE)
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
    fun validateToken(token: String, expectedTokenType: String): Boolean {
        return try {
            val claims = parseToken(token)
            claims.expiration.after(Date()) && claims[TOKEN_TYPE_CLAIM] == expectedTokenType
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
