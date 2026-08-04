package cn.esuny.orion.model.dto.file

/**
 * 头像上传确认响应
 */
data class AvatarConfirmResponse(
    /** 最终可访问的头像 URL（presigned GET 或 CDN） */
    val avatarUrl: String
)
