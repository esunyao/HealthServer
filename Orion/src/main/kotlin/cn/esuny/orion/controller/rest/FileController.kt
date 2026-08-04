package cn.esuny.orion.controller.rest

import cn.esuny.orion.model.dto.file.AvatarConfirmResponse
import cn.esuny.orion.model.dto.file.AvatarPresignRequest
import cn.esuny.orion.model.dto.file.PresignedUrlResponse
import cn.esuny.orion.model.result.ApiResponse
import cn.esuny.orion.service.FileService
import jakarta.validation.Valid
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestHeader
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

/**
 * 文件管理控制器
 *
 * 处理文件上传预签名、确认、访问等端点。
 * 路由：/v1/files/ **
 */
@RestController
@RequestMapping("/v1/files")
class FileController(private val fileService: FileService) {

    /**
     * 生成头像上传的预签名 URL
     *
     * POST /v1/files/avatar/presign
     */
    @PostMapping("/avatar/presign")
    fun presignAvatarUpload(
        @RequestHeader("X-User-Id") userId: Long,
        @RequestBody @Valid request: AvatarPresignRequest
    ): ApiResponse<PresignedUrlResponse> {
        val response = fileService.presignAvatarUpload(userId, request)
        return ApiResponse.success(data = response, message = "预签名 URL 生成成功")
    }

    /**
     * 确认头像上传完成
     *
     * POST /v1/files/avatar/confirm
     */
    @PostMapping("/avatar/confirm")
    fun confirmAvatarUpload(
        @RequestHeader("X-User-Id") userId: Long,
        @RequestBody objectKey: String
    ): ApiResponse<AvatarConfirmResponse> {
        val response = fileService.confirmAvatarUpload(userId, objectKey)
        return ApiResponse.success(data = response, message = "头像上传确认成功")
    }

    /**
     * 获取当前用户头像访问 URL
     *
     * GET /v1/files/avatar
     */
    @GetMapping("/avatar")
    fun getAvatarUrl(
        @RequestHeader("X-User-Id") userId: Long
    ): ApiResponse<String> {
        val avatarUrl = fileService.getAvatarUrl(userId)
        return ApiResponse.success(data = avatarUrl)
    }
}
