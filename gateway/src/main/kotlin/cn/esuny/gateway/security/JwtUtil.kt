package cn.esuny.gateway.security

import cn.esuny.gateway.config.JwtProperties
import io.jsonwebtoken.Claims
import io.jsonwebtoken.ExpiredJwtException
import io.jsonwebtoken.Jwts
import io.jsonwebtoken.security.Keys
import io.jsonwebtoken.security.SignatureException
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Component
import java.util.Date
import javax.crypto.SecretKey

/**
 * Gateway 专用的 JWT 工具类
 *
 * 只包含 Token 验证和解析功能，不包含签发功能。
 * 签发职责属于 Orion 模块。
 */
@Component
class JwtUtil(private val jwtProperties: JwtProperties) {

    companion object {
        private const val ACCESS_TOKEN_TYPE = "access"
        private const val TOKEN_TYPE_CLAIM = "tokenType"
    }

    private val log = LoggerFactory.getLogger(JwtUtil::class.java)

    private val key: SecretKey by lazy {
        Keys.hmacShaKeyFor(jwtProperties.secret.toByteArray())
    }

    /**
     * 验证 Token 是否有效（签名正确且未过期）
     */
    fun validateAccessToken(token: String): Boolean {
        return try {
            val claims = parseToken(token)
            claims.expiration.after(Date()) && claims[TOKEN_TYPE_CLAIM] == ACCESS_TOKEN_TYPE
        } catch (e: SignatureException) {
            log.debug("Invalid token signature: {}", e.message)
            false
        } catch (e: ExpiredJwtException) {
            log.debug("Token expired: {}", e.message)
            false
        } catch (e: Exception) {
            log.debug("Token validation failed: {}", e.message)
            false
        }
    }

    /**
     * 从 Token 中提取 userId（claims.subject）
     */
    fun getUserId(token: String): String {
        return parseToken(token).subject
    }

    /**
     * 从 Token 中提取 username
     */
    fun getUsername(token: String): String {
        return parseToken(token)["username"] as String
    }

    /**
     * 解析 Token，返回 Claims
     */
    private fun parseToken(token: String): Claims {
        return Jwts.parser()
            .verifyWith(key)
            .build()
            .parseSignedClaims(token)
            .payload
    }
}
