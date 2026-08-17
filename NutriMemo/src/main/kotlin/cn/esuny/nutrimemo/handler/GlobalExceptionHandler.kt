package cn.esuny.nutrimemo.handler

import cn.esuny.nutrimemo.model.ApiResponse
import org.slf4j.LoggerFactory
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.dao.DuplicateKeyException
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.http.converter.HttpMessageNotReadableException
import org.springframework.web.bind.MethodArgumentNotValidException
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.RestControllerAdvice
import org.springframework.web.servlet.resource.NoResourceFoundException
import java.sql.SQLException

@RestControllerAdvice
class GlobalExceptionHandler {
    private val log = LoggerFactory.getLogger(GlobalExceptionHandler::class.java)

    @ExceptionHandler(MethodArgumentNotValidException::class)
    fun validation(e: MethodArgumentNotValidException): ResponseEntity<ApiResponse<Nothing>> = respond(
        HttpStatus.BAD_REQUEST, 400, e.bindingResult.fieldErrors.joinToString("; ") { "${it.field}: ${it.defaultMessage}" }
    )

    @ExceptionHandler(HttpMessageNotReadableException::class)
    fun unreadable(): ResponseEntity<ApiResponse<Nothing>> = respond(HttpStatus.BAD_REQUEST, 400, "请求体格式无效")

    @ExceptionHandler(BusinessException::class)
    fun business(e: BusinessException): ResponseEntity<ApiResponse<Nothing>> = respond(e.httpStatus, e.code, e.message)

    @ExceptionHandler(DuplicateKeyException::class)
    fun duplicate(): ResponseEntity<ApiResponse<Nothing>> = respond(HttpStatus.CONFLICT, 409, "数据已存在，不能重复创建")

    @ExceptionHandler(DataIntegrityViolationException::class)
    fun integrity(e: DataIntegrityViolationException): ResponseEntity<ApiResponse<Nothing>> {
        val sqlState = findSqlState(e)
        if (sqlState?.startsWith("23") == true) {
            log.warn("Data integrity violation [sqlState={}]: {}", sqlState, e.rootCause?.message ?: e.message)
            return respond(HttpStatus.BAD_REQUEST, 400, "请求数据违反业务约束")
        }
        log.error("Database operation failed [sqlState={}]", sqlState, e)
        return respond(HttpStatus.INTERNAL_SERVER_ERROR, 500, "服务器内部错误，请联系管理员")
    }

    @ExceptionHandler(NoResourceFoundException::class)
    fun missing(): ResponseEntity<ApiResponse<Nothing>> = respond(HttpStatus.NOT_FOUND, 404, "接口或资源不存在")

    @ExceptionHandler(Exception::class)
    fun unknown(e: Exception): ResponseEntity<ApiResponse<Nothing>> {
        log.error("Unhandled NutriMemo error", e)
        return respond(HttpStatus.INTERNAL_SERVER_ERROR, 500, "服务器内部错误，请联系管理员")
    }

    private fun respond(status: HttpStatus, code: Int, message: String): ResponseEntity<ApiResponse<Nothing>> =
        ResponseEntity.status(status).body(ApiResponse.error(code, message))

    private fun findSqlState(error: Throwable): String? {
        var current: Throwable? = error
        while (current != null) {
            if (current is SQLException) return current.sqlState
            current = current.cause
        }
        return null
    }
}
