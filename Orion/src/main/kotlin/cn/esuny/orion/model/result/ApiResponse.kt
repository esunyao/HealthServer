package cn.esuny.orion.model.result

/**
 * 统一 API 响应格式的泛型包装类
 *
 * @param T 响应中包含的具体业务数据类型
 * @property code HTTP 风格的状态码
 * @property message 描述结果或错误原因
 * @property data 业务数据载荷，成功时包含实际数据，失败时为 null
 * @property traceId 全局请求链路追踪 ID
 * @property timestamp 服务器生成此响应的时间戳（毫秒）
 */
data class ApiResponse<T>(
    val code: Int,
    val message: String,
    val data: T? = null,
    val traceId: String? = null,
    val timestamp: Long = System.currentTimeMillis()
) {
    companion object {
        fun <T> success(data: T? = null, message: String = "Success"): ApiResponse<T> {
            return ApiResponse(code = 200, message = message, data = data)
        }

        fun <T> error(code: Int = 500, message: String = "Error", traceId: String? = null): ApiResponse<T> {
            return ApiResponse(code = code, message = message, data = null, traceId = traceId)
        }
    }
}
