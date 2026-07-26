package cn.esuny.gateway.handler

import cn.esuny.gateway.model.ApiResponse
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.HttpRequestMethodNotSupportedException
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.RestControllerAdvice
import org.springframework.web.servlet.NoHandlerFoundException

/**
 * 全局异常处理器 (Global Exception Handler)
 * 
 * 作用：统一处理应用中抛出的异常。
 * 当控制器 (Controller) 抛出异常时，会被此处的代码拦截，
 * 将错误信息包装成统一的 ApiResponse 格式并返回给客户端，而不是直接显示干巴巴的堆栈信息。
 * 这样做对前后端分离非常友好，前端可以依赖固定的结构进行错误提示。
 */
@RestControllerAdvice
class GlobalExceptionHandler {

    private val log = LoggerFactory.getLogger(GlobalExceptionHandler::class.java)

    /**
     * 处理 404 异常：当请求的路径不存在时触发
     */
    @ExceptionHandler(NoHandlerFoundException::class)
    fun handleNoHandlerFoundException(e: NoHandlerFoundException): ResponseEntity<ApiResponse<Nothing>> {
        log.warn("404 Not Found: {}", e.message)
        val apiResponse = ApiResponse.error<Nothing>(HttpStatus.NOT_FOUND.value(), "接口不存在: ${e.requestURL}")
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(apiResponse)
    }

    /**
     * 处理 405 异常：当请求方法不支持时触发 (比如接口是 POST，客户端用 GET 请求)
     */
    @ExceptionHandler(HttpRequestMethodNotSupportedException::class)
    fun handleHttpRequestMethodNotSupportedException(e: HttpRequestMethodNotSupportedException): ResponseEntity<ApiResponse<Nothing>> {
        log.warn("405 Method Not Allowed: {}", e.message)
        val apiResponse = ApiResponse.error<Nothing>(HttpStatus.METHOD_NOT_ALLOWED.value(), "不支持的请求方法: ${e.method}")
        return ResponseEntity.status(HttpStatus.METHOD_NOT_ALLOWED).body(apiResponse)
    }

    /**
     * 处理所有其他未捕获的异常 (Catch-all) -> 500 服务器内部错误
     * 主要是为了防止将系统底层的异常信息 (如 SQL 异常、NullPointerException) 暴露给外部调用者，
     * 同时在服务端记录详细的日志供排查问题。
     */
    @ExceptionHandler(Exception::class)
    fun handleException(e: Exception): ResponseEntity<ApiResponse<Nothing>> {
        log.error("500 Internal Server Error: ", e)
        val apiResponse = ApiResponse.error<Nothing>(HttpStatus.INTERNAL_SERVER_ERROR.value(), "服务器内部错误，请联系管理员")
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(apiResponse)
    }
}
