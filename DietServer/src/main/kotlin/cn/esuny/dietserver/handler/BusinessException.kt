package cn.esuny.dietserver.handler

import org.springframework.http.HttpStatus

/**
 * 自定义业务异常
 *
 * 用于在 Service 层抛出带有明确错误码和 HTTP 状态码的异常，
 * 由 [GlobalExceptionHandler] 统一拦截并转换为 ApiResponse。
 */
class BusinessException(
    val code: Int,
    override val message: String,
    val httpStatus: HttpStatus = HttpStatus.BAD_REQUEST
) : RuntimeException(message)
