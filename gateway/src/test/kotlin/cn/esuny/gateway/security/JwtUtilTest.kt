package cn.esuny.gateway.security

import cn.esuny.gateway.config.JwtProperties
import io.jsonwebtoken.Jwts
import io.jsonwebtoken.security.Keys
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import java.util.Date
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class JwtUtilTest {

    private lateinit var jwtUtil: JwtUtil

    @BeforeEach
    fun setUp() {
        val properties = JwtProperties().apply { secret = SECRET }
        jwtUtil = JwtUtil(properties)
    }

    @Test
    fun `gateway accepts access token only`() {
        assertTrue(jwtUtil.validateAccessToken(token("access")))
        assertFalse(jwtUtil.validateAccessToken(token("refresh")))
        assertFalse(jwtUtil.validateAccessToken(token(null)))
    }

    private fun token(tokenType: String?): String {
        val builder = Jwts.builder()
            .subject(USER_ID)
            .claim("username", USERNAME)
            .issuedAt(Date())
            .expiration(Date(System.currentTimeMillis() + 900_000))
        if (tokenType != null) {
            builder.claim("tokenType", tokenType)
        }
        return builder.signWith(Keys.hmacShaKeyFor(SECRET.toByteArray())).compact()
    }

    private companion object {
        const val SECRET = "HealthServer-Orion-JWT-Secret-Key-2026-For-Token-Generation"
        const val USER_ID = "user-id"
        const val USERNAME = "zhangsan"
    }
}