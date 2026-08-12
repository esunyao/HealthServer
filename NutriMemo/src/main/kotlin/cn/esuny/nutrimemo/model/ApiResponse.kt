package cn.esuny.nutrimemo.model

data class ApiResponse<T>(
    val code: Int,
    val message: String,
    val data: T? = null,
    val traceId: String? = null,
    val timestamp: Long = System.currentTimeMillis()
) {
    companion object {
        fun <T> success(data: T? = null, message: String = "Success") = ApiResponse(200, message, data)
        fun <T> created(data: T, message: String = "Created") = ApiResponse(201, message, data)
        fun <T> error(code: Int, message: String, traceId: String? = null) = ApiResponse<T>(code, message, null, traceId)
    }
}
