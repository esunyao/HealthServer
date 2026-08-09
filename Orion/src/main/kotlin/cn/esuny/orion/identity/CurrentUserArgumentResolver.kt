package cn.esuny.orion.identity

import cn.esuny.orion.handler.BusinessException
import cn.esuny.orion.service.IdentityProvisioningService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.core.MethodParameter
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import org.springframework.web.bind.support.WebDataBinderFactory
import org.springframework.web.context.request.NativeWebRequest
import org.springframework.web.method.support.HandlerMethodArgumentResolver
import org.springframework.web.method.support.ModelAndViewContainer
import java.util.UUID

@Component
class CurrentUserArgumentResolver(
    private val identityProvisioningService: IdentityProvisioningService
) : HandlerMethodArgumentResolver {

    override fun supportsParameter(parameter: MethodParameter): Boolean =
        parameter.hasParameterAnnotation(CurrentUser::class.java) && parameter.parameterType == AuthenticatedUser::class.java

    override fun resolveArgument(
        parameter: MethodParameter,
        mavContainer: ModelAndViewContainer?,
        webRequest: NativeWebRequest,
        binderFactory: WebDataBinderFactory?
    ): AuthenticatedUser {
        val request = webRequest.getNativeRequest(HttpServletRequest::class.java)
            ?: throw BusinessException(401, "缺少 HTTP 请求上下文", HttpStatus.UNAUTHORIZED)
        if (request.getHeader(HEADER_GATEWAY_SOURCE) != GATEWAY_SOURCE) {
            throw BusinessException(401, "请求必须经由 Gateway", HttpStatus.UNAUTHORIZED)
        }

        val user = AuthenticatedUser(
            userId = parseSubject(request.getHeader(HEADER_SUBJECT)),
            username = requiredHeader(request, HEADER_USERNAME),
            email = request.getHeader(HEADER_EMAIL)?.trim()?.ifBlank { null },
            emailVerified = request.getHeader(HEADER_EMAIL_VERIFIED).equals("true", ignoreCase = true),
            displayName = request.getHeader(HEADER_DISPLAY_NAME)?.trim().orEmpty()
        )
        identityProvisioningService.provision(user)
        return user
    }

    private fun parseSubject(raw: String?): UUID = try {
        UUID.fromString(raw)
    } catch (_: Exception) {
        throw BusinessException(401, "身份主体无效", HttpStatus.UNAUTHORIZED)
    }

    private fun requiredHeader(request: HttpServletRequest, name: String): String = request.getHeader(name)
        ?.trim()
        ?.takeIf(String::isNotEmpty)
        ?: throw BusinessException(401, "缺少可信身份字段", HttpStatus.UNAUTHORIZED)

    companion object {
        const val HEADER_GATEWAY_SOURCE = "X-Gateway-Source"
        const val HEADER_SUBJECT = "X-Auth-Subject"
        const val HEADER_USERNAME = "X-Auth-Username"
        const val HEADER_EMAIL = "X-Auth-Email"
        const val HEADER_EMAIL_VERIFIED = "X-Auth-Email-Verified"
        const val HEADER_DISPLAY_NAME = "X-Auth-Display-Name"
        const val GATEWAY_SOURCE = "HealthServer-Gateway"
    }
}
