package cn.esuny.orion.controller.rest

import cn.esuny.orion.model.dto.file.AvatarPresignRequest
import cn.esuny.orion.model.dto.file.PresignedUrlResponse
import cn.esuny.orion.model.dto.file.AvatarConfirmResponse
import cn.esuny.orion.service.FileService
import tools.jackson.databind.ObjectMapper
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.ArgumentMatchers.anyLong
import org.mockito.ArgumentMatchers.anyString
import org.mockito.Mockito.verify
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.http.MediaType
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.*

@WebMvcTest(FileController::class)
class FileControllerTest {

    @Autowired
    lateinit var mockMvc: MockMvc

    @Autowired
    lateinit var objectMapper: ObjectMapper

    @MockitoBean
    lateinit var fileService: FileService

    private val testUserId = 123L

//    @Test
    fun `presign avatar upload should return presigned URL`() {
        // Given
        val request = AvatarPresignRequest(fileName = "avatar.jpg", contentType = "image/jpeg")
        val response = PresignedUrlResponse(
            uploadUrl = "http://localhost:9000/bucket/avatar-staging/123/test.jpg?X-Amz-Algorithm=...",
            objectKey = "avatar-staging/123/test.jpg",
            expiresIn = 300
        )

        given(fileService.presignAvatarUpload(testUserId, request)).willReturn(response)

        // When & Then
        mockMvc.perform(
            post("/v1/files/avatar/presign")
                .header("X-User-Id", testUserId)
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(request))
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.code").value(200))
            .andExpect(jsonPath("$.data.uploadUrl").exists())
            .andExpect(jsonPath("$.data.objectKey").exists())
    }

//    @Test
    fun `confirm avatar upload should pass decoded staging key to service`() {
        // Given
        val objectKey = "avatar-staging/123/test.jpg"
        val response = AvatarConfirmResponse(avatarUrl = "http://localhost:9000/bucket/$objectKey?signed")

        given(fileService.confirmAvatarUpload(anyLong(), anyString())).willReturn(response)

        // When & Then
        mockMvc.perform(
            post("/v1/files/avatar/confirm")
                .header("X-User-Id", testUserId)
                .contentType(MediaType.APPLICATION_JSON)
                .content("\"$objectKey\"")
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.code").value(200))
            .andExpect(jsonPath("$.data.avatarUrl").exists())

        verify(fileService).confirmAvatarUpload(testUserId, objectKey)
    }

//    @Test
    fun `confirm avatar upload should reject non string or empty bodies`() {
        listOf(
            "null",
            "\"\"",
            "{\"objectKey\":\"avatar-staging/123/test.jpg\"}",
            "not-json"
        ).forEach { body ->
            mockMvc.perform(
                post("/v1/files/avatar/confirm")
                    .header("X-User-Id", testUserId)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body)
            )
                .andExpect(status().isBadRequest)
                .andExpect(jsonPath("$.code").value(400))
        }
    }

//    @Test
    fun `get avatar URL should return avatar URL`() {
        // Given
        val avatarUrl = "http://localhost:9000/bucket/avatars/123/test.jpg?signed"
        given(fileService.getAvatarUrl(testUserId)).willReturn(avatarUrl)

        // When & Then
        mockMvc.perform(
            get("/v1/files/avatar")
                .header("X-User-Id", testUserId)
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.code").value(200))
            .andExpect(jsonPath("$.data").value(avatarUrl))
    }
}
