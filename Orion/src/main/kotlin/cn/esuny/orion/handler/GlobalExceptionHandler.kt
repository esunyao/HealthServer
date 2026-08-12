package cn.esuny.orion.handler

import cn.esuny.orion.model.result.ApiResponse
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.dao.DuplicateKeyException
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.http.converter.HttpMessageNotReadableException
import org.springframework.web.bind.MethodArgumentNotValidException
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.RestControllerAdvice
import org.springframework.web.servlet.resource.NoResourceFoundException

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
     * 处理数据库唯一约束冲突。客户端请求本身有效，但不能创建重复业务记录。
     */
    @ExceptionHandler(DuplicateKeyException::class)
    fun handleDuplicateKey(e: DuplicateKeyException): ResponseEntity<ApiResponse<Nothing>> {
        val message = if (e.message?.contains("uq_health_goals_active_type") == true) {
            "该类型的有效健康目标已存在"
        } else {
            "数据已存在，不能重复创建"
        }
        log.warn("409 Conflict: {}", message)
        return ResponseEntity.status(HttpStatus.CONFLICT).body(ApiResponse.error(409, message))
    }

    /**
     * 处理数据库检查约束等数据完整性错误，避免把客户端输入错误记录为 500。
     */
    @ExceptionHandler(DataIntegrityViolationException::class)
    fun handleDataIntegrityViolation(e: DataIntegrityViolationException): ResponseEntity<ApiResponse<Nothing>> {
        log.warn("400 Data Integrity Violation: {}", e.rootCause?.message ?: e.message)
        return ResponseEntity.badRequest().body(ApiResponse.error(400, "请求数据违反业务约束"))
    }

    /**
     * 处理不存在的接口或静态资源请求。
     */
    @ExceptionHandler(NoResourceFoundException::class)
    fun handleNoResourceFound(e: NoResourceFoundException): ResponseEntity<ApiResponse<Nothing>> {
        log.warn("404 Resource Not Found: {}", e.message)
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(ApiResponse.error(404, "接口或资源不存在"))
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
