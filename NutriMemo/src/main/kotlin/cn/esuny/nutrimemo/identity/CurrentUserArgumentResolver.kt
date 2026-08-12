package cn.esuny.nutrimemo.identity

import cn.esuny.nutrimemo.handler.BusinessException
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
class CurrentUserArgumentResolver : HandlerMethodArgumentResolver {
    override fun supportsParameter(parameter: MethodParameter) =
        parameter.hasParameterAnnotation(CurrentUser::class.java) && parameter.parameterType == AuthenticatedUser::class.java

    override fun resolveArgument(
        parameter: MethodParameter,
        mavContainer: ModelAndViewContainer?,
        webRequest: NativeWebRequest,
        binderFactory: WebDataBinderFactory?
    ): AuthenticatedUser {
        val request = webRequest.getNativeRequest(HttpServletRequest::class.java)
            ?: throw BusinessException(401, "缺少 HTTP 请求上下文", HttpStatus.UNAUTHORIZED)
        if (request.getHeader(GATEWAY_HEADER) != GATEWAY_SOURCE) {
            throw BusinessException(401, "请求必须经由 Gateway", HttpStatus.UNAUTHORIZED)
        }
        val id = try {
            UUID.fromString(request.getHeader(SUBJECT_HEADER)?.trim())
        } catch (_: Exception) {
            throw BusinessException(401, "身份主体无效", HttpStatus.UNAUTHORIZED)
        }
        return AuthenticatedUser(id)
    }

    companion object {
        const val GATEWAY_HEADER = "X-Gateway-Source"
        const val SUBJECT_HEADER = "X-Auth-Subject"
        const val GATEWAY_SOURCE = "HealthServer-Gateway"
    }
}
