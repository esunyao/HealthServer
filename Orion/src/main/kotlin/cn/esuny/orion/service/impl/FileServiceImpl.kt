package cn.esuny.orion.service.impl

import cn.esuny.orion.config.OssProperties
import cn.esuny.orion.handler.BusinessException
import cn.esuny.orion.mapper.UserMapper
import cn.esuny.orion.model.dto.file.AvatarConfirmResponse
import cn.esuny.orion.model.dto.file.AvatarPresignRequest
import cn.esuny.orion.model.dto.file.PresignedUrlResponse
import cn.esuny.orion.service.FileService
import cn.esuny.orion.service.FileCleanupTaskService
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.model.GetObjectRequest
import software.amazon.awssdk.services.s3.model.HeadObjectRequest
import software.amazon.awssdk.services.s3.model.PutObjectRequest
import software.amazon.awssdk.services.s3.model.CopyObjectRequest
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest
import java.time.Duration
import java.time.OffsetDateTime
import java.util.UUID

/**
 * 文件管理业务实现
 *
 * 实现文件上传预签名、确认、访问等功能
 */
@Service
class FileServiceImpl(
    private val s3Client: S3Client,
    private val s3Presigner: S3Presigner,
    private val ossProperties: OssProperties,
    private val userMapper: UserMapper,
    private val fileCleanupTaskService: FileCleanupTaskService
) : FileService {

    private val log = LoggerFactory.getLogger(FileServiceImpl::class.java)

    /**
     * 生成头像上传的预签名 PUT URL
     */
    override fun presignAvatarUpload(userId: UUID, request: AvatarPresignRequest): PresignedUrlResponse {
        // 1. 验证 Content-Type
        if (request.contentType !in ossProperties.allowedContentTypes) {
            throw BusinessException(
                code = 400,
                message = "不允许的文件类型: ${request.contentType}，仅支持 ${ossProperties.allowedContentTypes.joinToString()}",
                httpStatus = HttpStatus.BAD_REQUEST
            )
        }

        // 2. 生成临时对象 key；未确认的对象由 RustFS 生命周期规则自动清理
        val objectKey = createObjectKey("avatar-staging", userId, extractExtension(request.fileName))

        // 3. 构建预签名请求
        val presignRequest = PutObjectPresignRequest.builder()
            .signatureDuration(ossProperties.presignedExpiration)
            .putObjectRequest(
                PutObjectRequest.builder()
                    .bucket(ossProperties.bucket)
                    .key(objectKey)
                    .contentType(request.contentType)
                    .build()
            )
            .build()

        // 4. 生成预签名 URL
        val presignedRequest = s3Presigner.presignPutObject(presignRequest)
        val presignedUrl = presignedRequest.url().toString()

        log.info("生成头像上传预签名 URL: userId={}, objectKey={}", userId, objectKey)

        return PresignedUrlResponse(
            uploadUrl = presignedUrl,
            objectKey = objectKey,
            expiresIn = ossProperties.presignedExpiration.toSeconds()
        )
    }

    /**
     * 确认头像上传完成，更新用户 avatarUrl
     */
    @Transactional
    override fun confirmAvatarUpload(userId: UUID, objectKey: String): AvatarConfirmResponse {
        // 1. 验证临时对象 key 前缀
        if (!objectKey.startsWith("avatar-staging/$userId/")) {
            throw BusinessException(
                code = 403,
                message = "对象 key 无效: objectKey 必须以 'avatar-staging/$userId/' 开头",
                httpStatus = HttpStatus.FORBIDDEN
            )
        }

        // 2. 验证临时文件存在、类型和大小
        val headObject = try {
            val headRequest = HeadObjectRequest.builder()
                .bucket(ossProperties.bucket)
                .key(objectKey)
                .build()
            s3Client.headObject(headRequest)
        } catch (e: Exception) {
            throw BusinessException(
                code = 404,
                message = "文件不存在或上传失败: $objectKey",
                httpStatus = HttpStatus.NOT_FOUND
            )
        }

        if (headObject.contentType() !in ossProperties.allowedContentTypes ||
            headObject.contentLength() == null ||
            headObject.contentLength() > ossProperties.maxFileSize
        ) {
            throw BusinessException(400, "头像文件类型或大小不符合要求", HttpStatus.BAD_REQUEST)
        }

        // 3. RustFS 内部复制到新的正式对象，文件内容不经过 Orion
        val finalObjectKey = createObjectKey("avatars", userId, extractExtension(objectKey))
        s3Client.copyObject(
            CopyObjectRequest.builder()
                .sourceBucket(ossProperties.bucket)
                .sourceKey(objectKey)
                .destinationBucket(ossProperties.bucket)
                .destinationKey(finalObjectKey)
                .build()
        )

        // 4. 锁定用户行后切换引用，并在同一事务写入清理任务
        val user = userMapper.selectByIdForUpdate(userId)
            ?: throw BusinessException(
                code = 404,
                message = "用户不存在",
                httpStatus = HttpStatus.NOT_FOUND
            )

        val updated = user.copy(
            avatarObjectKey = finalObjectKey
        )
        userMapper.updateById(updated)

        if (user.avatarObjectKey != null && user.avatarObjectKey != finalObjectKey) {
            fileCleanupTaskService.enqueueOldAvatar(ossProperties.bucket, user.avatarObjectKey, userId)
        }
        fileCleanupTaskService.enqueueStagingSource(ossProperties.bucket, objectKey, userId)

        log.info("用户头像更新成功: userId={}, objectKey={}", userId, finalObjectKey)

        // 5. 返回头像访问 URL
        val avatarUrl = generateAvatarDownloadUrl(userId, finalObjectKey)
        return AvatarConfirmResponse(avatarUrl = avatarUrl)
    }

    /**
     * 获取当前用户头像的访问 URL
     */
    override fun getAvatarUrl(userId: UUID): String {
        val user = userMapper.selectById(userId)
            ?: throw BusinessException(
                code = 404,
                message = "用户不存在",
                httpStatus = HttpStatus.NOT_FOUND
            )

        val objectKey = user.avatarObjectKey ?: run {
            throw BusinessException(
                code = 404,
                message = "用户未设置头像",
                httpStatus = HttpStatus.NOT_FOUND
            )
        }

        return generateAvatarDownloadUrl(userId, objectKey)
    }

    /**
     * 生成头像访问的 presigned GET URL
     */
    private fun generateAvatarDownloadUrl(userId: UUID, objectKey: String): String {
        // 如果配置了 CDN 域名，直接返回 CDN URL
        if (ossProperties.cdnDomain != null) {
            return "${ossProperties.cdnDomain}/$objectKey"
        }

        // 否则生成 presigned GET URL
        val presignRequest = GetObjectPresignRequest.builder()
            .signatureDuration(Duration.ofHours(1))  // 访问 URL 有效期 1 小时
            .getObjectRequest(
                GetObjectRequest.builder()
                    .bucket(ossProperties.bucket)
                    .key(objectKey)
                    .build()
            )
            .build()

        val presignedRequest = s3Presigner.presignGetObject(presignRequest)
        return presignedRequest.url().toString()
    }

    /**
     * 从文件名提取扩展名
     */
    private fun extractExtension(fileName: String): String {
        val lastDotIndex = fileName.lastIndexOf('.')
        if (lastDotIndex == -1 || lastDotIndex == fileName.length - 1) {
            return "jpg"  // 默认扩展名
        }
        return fileName.substring(lastDotIndex + 1).lowercase()
    }

    private fun createObjectKey(prefix: String, userId: UUID, extension: String): String {
        val timestamp = System.currentTimeMillis()
        val uuid = UUID.randomUUID().toString().substring(0, 8)
        return "$prefix/$userId/${timestamp}_${uuid}.$extension"
    }
}
