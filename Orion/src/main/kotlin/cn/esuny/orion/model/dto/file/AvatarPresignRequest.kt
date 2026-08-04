package cn.esuny.orion.model.dto.file

import jakarta.validation.constraints.NotBlank

/**
 * 头像上传预签名请求
 */
data class AvatarPresignRequest(
    /** 原始文件名 */
    @NotBlank
    val fileName: String,

    /** MIME 类型 */
    @NotBlank
    val contentType: String
)
