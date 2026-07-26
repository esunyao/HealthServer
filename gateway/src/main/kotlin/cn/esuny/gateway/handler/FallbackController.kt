package cn.esuny.gateway.handler

import cn.esuny.gateway.model.ApiResponse
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

/**
 * 降级回调控制器 (Fallback Controller)
 * 
 * 作用：在使用熔断器 (如 Resilience4j 或 Sentinel) 保护微服务时，
 * 如果下游的微服务不可用（宕机、超时或出错率过高），熔断器会拦截请求，
 * 并将其转发（降级）到这个 `/fallback` 端点。
 * 
 * 这样就可以给客户端返回一个友好的提示（比如“服务暂时不可用”），
 * 而不是让客户端无休止地等待或者收到原始的错误。
 */
@RestController
class FallbackController {

    /**
     * 统一的降级处理接口
     */
    @RequestMapping("/fallback")
    fun fallback(): ResponseEntity<ApiResponse<Nothing>> {
        // 返回 HTTP 503 (Service Unavailable) 状态码，表示服务当前不可用
        val apiResponse = ApiResponse.error<Nothing>(503, "服务暂时不可用，请稍后重试")
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(apiResponse)
    }
}
