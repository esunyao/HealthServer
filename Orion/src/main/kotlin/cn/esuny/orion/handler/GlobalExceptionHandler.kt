package cn.esuny.orion.handler

import cn.esuny.orion.model.result.ApiResponse
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.http.converter.HttpMessageNotReadableException
import org.springframework.web.bind.MethodArgumentNotValidException
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.RestControllerAdvice

/**
 * 全局异常处理器
 *
 * 统一拦截 Controller 层抛出的异常，包装为 ApiResponse 格式返回给客户端。
 */
@RestControllerAdvice
class GlobalExceptionHandler {

    private val log = LoggerFactory.getLogger(GlobalExceptionHandler::class.java)

    /**
     * 处理参数校验异常（@Valid 失败）
     */
    @ExceptionHandler(MethodArgumentNotValidException::class)
    fun handleValidationException(e: MethodArgumentNotValidException): ResponseEntity<ApiResponse<Nothing>> {
        val message = e.bindingResult.fieldErrors.joinToString("; ") { "${it.field}: ${it.defaultMessage}" }
        log.warn("400 Validation Failed: {}", message)
        return ResponseEntity.badRequest().body(ApiResponse.error(400, message))
    }

    /**
     * 处理无法解析的 JSON 请求体，避免错误请求被包装成 500。
     */
    @ExceptionHandler(HttpMessageNotReadableException::class)
    fun handleUnreadableMessage(e: HttpMessageNotReadableException): ResponseEntity<ApiResponse<Nothing>> {
        log.warn("400 Malformed Request Body: {}", e.message)
        return ResponseEntity.badRequest().body(ApiResponse.error(400, "请求体格式无效"))
    }

    /**
     * 处理业务异常（自定义 BusinessException）
     */
    @ExceptionHandler(BusinessException::class)
    fun handleBusinessException(e: BusinessException): ResponseEntity<ApiResponse<Nothing>> {
        log.warn("Business Exception [{}]: {}", e.code, e.message)
        return ResponseEntity.status(e.httpStatus).body(ApiResponse.error(e.code, e.message))
    }

    /**
     * 处理所有其他未捕获的异常
     */
    @ExceptionHandler(Exception::class)
    fun handleException(e: Exception): ResponseEntity<ApiResponse<Nothing>> {
        log.error("500 Internal Server Error: ", e)
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(ApiResponse.error(500, "服务器内部错误，请联系管理员"))
    }
}
