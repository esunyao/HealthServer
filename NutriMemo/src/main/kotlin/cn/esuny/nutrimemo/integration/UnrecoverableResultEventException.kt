package cn.esuny.nutrimemo.integration

class UnrecoverableResultEventException(
    val reasonCode: String,
    message: String,
    cause: Throwable? = null,
) : RuntimeException(message, cause)
