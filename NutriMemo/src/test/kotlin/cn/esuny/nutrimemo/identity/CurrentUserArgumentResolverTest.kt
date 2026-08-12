package cn.esuny.nutrimemo.identity

import cn.esuny.nutrimemo.handler.BusinessException
import io.mockk.every
import io.mockk.mockk
import jakarta.servlet.http.HttpServletRequest
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.core.MethodParameter
import org.springframework.web.context.request.NativeWebRequest
import java.util.UUID
import kotlin.test.assertEquals

class CurrentUserArgumentResolverTest {
    private val resolver = CurrentUserArgumentResolver()
    private val id = UUID.fromString("d290f1ee-6c54-4b01-90e6-d701748f0851")

    @Test
    fun `accepts only gateway source and UUID subject`() {
        val request = mockk<HttpServletRequest>()
        every { request.getHeader("X-Gateway-Source") } returns "HealthServer-Gateway"
        every { request.getHeader("X-Auth-Subject") } returns id.toString()
        val web = mockk<NativeWebRequest>()
        every { web.getNativeRequest(HttpServletRequest::class.java) } returns request

        assertEquals(id, resolver.resolveArgument(mockk<MethodParameter>(), null, web, null).userId)
    }

    @Test
    fun `rejects direct request or malformed subject`() {
        val request = mockk<HttpServletRequest>()
        every { request.getHeader("X-Gateway-Source") } returns "forged"
        val web = mockk<NativeWebRequest>()
        every { web.getNativeRequest(HttpServletRequest::class.java) } returns request
        assertEquals(401, assertThrows<BusinessException> { resolver.resolveArgument(mockk(), null, web, null) }.code)
    }
}
