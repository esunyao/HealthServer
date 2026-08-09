package cn.esuny.orion.service

import cn.esuny.orion.model.dto.file.AvatarConfirmResponse
import cn.esuny.orion.model.dto.file.AvatarPresignRequest
import cn.esuny.orion.model.dto.file.PresignedUrlResponse
import java.util.UUID

/**
 * 文件管理业务接口
 *
 * 处理文件上传、确认、访问等功能
 */
interface FileService {

    /**
     * 生成头像上传的预签名 PUT URL
     *
     * @param userId 用户 ID
     * @param request 上传请求（包含文件名和 Content-Type）
     * @return 预签名 URL 和对象 key
     */
    fun presignAvatarUpload(userId: UUID, request: AvatarPresignRequest): PresignedUrlResponse

    /**
     * 确认头像上传完成，更新用户 avatarUrl
     *
     * @param userId 用户 ID
     * @param objectKey 上传的文件对象 key
     * @return 头像访问 URL
     */
    fun confirmAvatarUpload(userId: UUID, objectKey: String): AvatarConfirmResponse

    /**
     * 获取当前用户头像的访问 URL
     *
     * @param userId 用户 ID
     * @return 头像访问 URL（presigned GET 或 CDN）
     */
    fun getAvatarUrl(userId: UUID): String
}
