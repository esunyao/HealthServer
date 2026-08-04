package cn.esuny.orion.model.dto.file

/**
 * 预签名上传 URL 响应
 */
data class PresignedUrlResponse(
    /** 预签名 PUT URL */
    val uploadUrl: String,

    /** 对象 key（客户端上传后需回传） */
    val objectKey: String,

    /** URL 有效期（秒） */
    val expiresIn: Long
)
