package cn.esuny.gateway.model

/**
 * 统一 API 响应格式的泛型包装类
 *
 * 在前后端分离的项目中，为了方便前端统一处理请求的结果（例如弹窗提示、加载状态等），
 * 后端需要返回结构固定的 JSON 报文。这就是此类存在的目的。
 * 
 * @param T 响应中包含的具体业务数据类型
 * @property code HTTP风格的状态码。比如 200 代表成功，400 或 500 代表失败。
 * @property message 给人看的消息提示，用于描述结果或者错误原因。
 * @property data 业务数据载荷。成功时包含实际数据，失败时一般为 null。
 * @property traceId 全局请求链路追踪ID，当出现问题时，开发人员可以通过这个ID在日志中查到具体的请求细节。
 * @property timestamp 服务器生成此响应的时间戳，即从 1970-01-01 开始的毫秒数。
 */
data class ApiResponse<T>(
    val code: Int,
    val message: String,
    val data: T? = null,
    val traceId: String? = null,
    val timestamp: Long = System.currentTimeMillis()
) {
    companion object {
        /**
         * 创建一个表示成功的响应对象。
         *
         * @param data 要返回给客户端的实际数据
         * @param message 成功提示消息，默认为 "Success"
         * @return 状态码为 200 的统一响应体
         */
        fun <T> success(data: T? = null, message: String = "Success"): ApiResponse<T> {
            return ApiResponse(
                code = 200,
                message = message,
                data = data
            )
        }

        /**
         * 创建一个表示失败的响应对象。
         *
         * @param code 错误码，通常非 200，比如 400（请求错误）、401（未授权）、500（服务器异常）等
         * @param message 错误详情或提示，默认为 "Error"
         * @param traceId 当前请求的链路ID，方便排查问题
         * @return 包含错误信息的统一响应体
         */
        fun <T> error(code: Int = 500, message: String = "Error", traceId: String? = null): ApiResponse<T> {
            return ApiResponse(
                code = code,
                message = message,
                data = null,
                traceId = traceId
            )
        }
    }
}
