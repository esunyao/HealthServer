package cn.esuny.healthmind.domain.task

class UnrecoverableCaptureEventException(
    message: String,
    cause: Throwable? = null,
) : RuntimeException(message, cause)
