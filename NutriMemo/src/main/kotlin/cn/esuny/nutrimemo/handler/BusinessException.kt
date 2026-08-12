package cn.esuny.nutrimemo.handler

import org.springframework.http.HttpStatus

class BusinessException(
    val code: Int,
    override val message: String,
    val httpStatus: HttpStatus = HttpStatus.BAD_REQUEST
) : RuntimeException(message)
