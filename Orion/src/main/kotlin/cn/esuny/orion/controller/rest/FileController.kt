package cn.esuny.orion.controller.rest

import cn.esuny.orion.handler.BusinessException
import cn.esuny.orion.identity.AuthenticatedUser
import cn.esuny.orion.identity.CurrentUser
import cn.esuny.orion.model.dto.file.AvatarConfirmResponse
import cn.esuny.orion.model.dto.file.AvatarPresignRequest
import cn.esuny.orion.model.dto.file.PresignedUrlResponse
import cn.esuny.orion.model.result.ApiResponse
import cn.esuny.orion.service.FileService
import jakarta.validation.Valid
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController
import tools.jackson.databind.JsonNode

@RestController
@RequestMapping("/v1/files")
class FileController(private val fileService: FileService) {
    @PostMapping("/avatar/presign")
    fun presignAvatarUpload(
        @CurrentUser user: AuthenticatedUser,
        @RequestBody @Valid request: AvatarPresignRequest
    ): ApiResponse<PresignedUrlResponse> = ApiResponse.success(
        data = fileService.presignAvatarUpload(user.userId, request), message = "预签名 URL 生成成功"
    )

    @PostMapping("/avatar/confirm")
    fun confirmAvatarUpload(@CurrentUser user: AuthenticatedUser, @RequestBody body: JsonNode?): ApiResponse<AvatarConfirmResponse> {
        val objectKey = body?.takeIf { it.isTextual }?.textValue()?.takeIf { it.isNotBlank() }
            ?: throw BusinessException(400, "objectKey 必须是非空 JSON 字符串")
        return ApiResponse.success(data = fileService.confirmAvatarUpload(user.userId, objectKey), message = "头像上传确认成功")
    }

    @GetMapping("/avatar")
    fun getAvatarUrl(@CurrentUser user: AuthenticatedUser): ApiResponse<String> =
        ApiResponse.success(data = fileService.getAvatarUrl(user.userId))
}
