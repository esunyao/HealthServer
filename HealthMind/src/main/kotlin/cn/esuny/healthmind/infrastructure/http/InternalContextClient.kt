package cn.esuny.healthmind.infrastructure.http

import cn.esuny.healthmind.application.port.out.InternalContextPort
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.database.ToolInvocationRepository
import cn.esuny.healthmind.infrastructure.oauth.ClientCredentialsTokenProvider
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import tools.jackson.databind.JsonNode

@Component
class InternalContextClient(
    @Qualifier("internalRestClientBuilder") builder: RestClient.Builder,
    private val tokens: ClientCredentialsTokenProvider,
    private val properties: HealthMindProperties,
) : InternalContextPort {
    private val builder = builder

    override fun getNutritionContext(grant: ToolInvocationRepository.ToolGrant): JsonNode {
        val subjectId = requireNotNull(grant.subjectId) { "Task has no subject_id" }
        return post(
            properties.oauth.orion,
            "/internal/v1/ai-context/nutrition",
            mapOf("subject_id" to subjectId.toString(), "task_id" to grant.taskId.toString()),
        )
    }

    override fun getCaptureContext(grant: ToolInvocationRepository.ToolGrant): JsonNode = post(
        properties.oauth.nutrimemo,
        "/internal/v1/analysis-context/capture",
        mapOf(
            "subject_id" to requireNotNull(grant.subjectId).toString(),
            "capture_session_id" to grant.captureSessionId.toString(),
            "meal_id" to grant.mealId,
            "task_id" to grant.taskId.toString(),
        ),
    )

    private fun post(config: HealthMindProperties.OAuth.Client, path: String, body: Any): JsonNode =
        builder.clone().baseUrl(config.baseUrl).build().post().uri(path)
            .header("Authorization", "Bearer ${tokens.token(config)}")
            .body(body)
            .retrieve()
            .body(JsonNode::class.java)
            ?: error("Internal context service returned an empty response")
}
