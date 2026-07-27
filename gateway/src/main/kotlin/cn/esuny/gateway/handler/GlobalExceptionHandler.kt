package cn.esuny.gateway.handler

import cn.esuny.gateway.model.ApiResponse
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.RestControllerAdvice
import org.springframework.web.server.MethodNotAllowedException
import org.springframework.web.server.ResponseStatusException
import org.springframework.web.server.ServerWebExchange

/**
 * 全局异常处理器 (Global Exception Handler)
 *
 * 作用：统一处理应用中抛出的异常。
 * 当控制器 (Controller) 抛出异常时，会被此处的代码拦截，
 * 将错误信息包装成统一的 ApiResponse 格式并返回给客户端。
 */
@RestControllerAdvice
class GlobalExceptionHandler {

    private val log = LoggerFactory.getLogger(GlobalExceptionHandler::class.java)

    /**
     * 处理 404 异常：当请求的路径不存在时触发
     */
    @ExceptionHandler(ResponseStatusException::class)
    fun handleResponseStatusException(e: ResponseStatusException): ResponseEntity<ApiResponse<Nothing>> {
        log.warn("{} {}: {}", e.statusCode.value(), e.reason ?: "Not Found", e.message)
        val apiResponse = ApiResponse.error<Nothing>(
            e.statusCode.value(),
            "接口不存在: ${e.reason ?: "Not Found"}"
        )
        return ResponseEntity.status(e.statusCode).body(apiResponse)
    }

    /**
     * 处理 405 异常：当请求方法不支持时触发
     */
    @ExceptionHandler(MethodNotAllowedException::class)
    fun handleMethodNotAllowedException(e: MethodNotAllowedException): ResponseEntity<ApiResponse<Nothing>> {
        log.warn("405 Method Not Allowed: {}", e.message)
        val apiResponse = ApiResponse.error<Nothing>(405, "不支持的请求方法")
        return ResponseEntity.status(HttpStatus.METHOD_NOT_ALLOWED).body(apiResponse)
    }

    /**
     * 处理所有其他未捕获的异常 (Catch-all) -> 500 服务器内部错误
     */
    @ExceptionHandler(Exception::class)
    fun handleException(e: Exception): ResponseEntity<ApiResponse<Nothing>> {
        log.error("500 Internal Server Error: ", e)
        val apiResponse = ApiResponse.error<Nothing>(500, "服务器内部错误，请联系管理员")
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(apiResponse)
    }
}
