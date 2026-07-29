package cn.esuny.orion.util

import io.jsonwebtoken.Jwts
import io.jsonwebtoken.security.Keys
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.test.util.ReflectionTestUtils
import java.util.Date
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class JwtUtilTest {

    private lateinit var jwtUtil: JwtUtil

    @BeforeEach
    fun setUp() {
        jwtUtil = JwtUtil()
        ReflectionTestUtils.setField(jwtUtil, "secret", SECRET)
        ReflectionTestUtils.setField(jwtUtil, "accessTokenExpiration", 900_000L)
        ReflectionTestUtils.setField(jwtUtil, "refreshTokenExpiration", 604_800_000L)
    }

    @Test
    fun `generated tokens have distinct token types`() {
        val accessToken = jwtUtil.generateAccessToken(USER_ID, USERNAME)
        val refreshToken = jwtUtil.generateRefreshToken(USER_ID, USERNAME)

        assertEquals(JwtUtil.ACCESS_TOKEN_TYPE, jwtUtil.parseToken(accessToken)["tokenType"])
        assertEquals(JwtUtil.REFRESH_TOKEN_TYPE, jwtUtil.parseToken(refreshToken)["tokenType"])
    }

    @Test
    fun `validation only accepts the expected token type`() {
        val accessToken = jwtUtil.generateAccessToken(USER_ID, USERNAME)
        val refreshToken = jwtUtil.generateRefreshToken(USER_ID, USERNAME)

        assertTrue(jwtUtil.validateToken(accessToken, JwtUtil.ACCESS_TOKEN_TYPE))
        assertFalse(jwtUtil.validateToken(accessToken, JwtUtil.REFRESH_TOKEN_TYPE))
        assertTrue(jwtUtil.validateToken(refreshToken, JwtUtil.REFRESH_TOKEN_TYPE))
        assertFalse(jwtUtil.validateToken(refreshToken, JwtUtil.ACCESS_TOKEN_TYPE))
    }

    @Test
    fun `legacy token without token type is rejected`() {
        val legacyToken = Jwts.builder()
            .subject(USER_ID)
            .claim("username", USERNAME)
            .issuedAt(Date())
            .expiration(Date(System.currentTimeMillis() + 900_000))
            .signWith(Keys.hmacShaKeyFor(SECRET.toByteArray()))
            .compact()

        assertFalse(jwtUtil.validateToken(legacyToken, JwtUtil.ACCESS_TOKEN_TYPE))
        assertFalse(jwtUtil.validateToken(legacyToken, JwtUtil.REFRESH_TOKEN_TYPE))
    }

    private companion object {
        const val SECRET = "HealthServer-Orion-JWT-Secret-Key-2026-For-Token-Generation"
        const val USER_ID = "user-id"
        const val USERNAME = "zhangsan"
    }
}