package cn.esuny.healthmind.infrastructure.dify

import cn.esuny.healthmind.application.port.out.DifyWorkflowPort
import cn.esuny.healthmind.domain.task.DifyWorkflowResult
import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.domain.task.TaskExecutionException
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import org.springframework.http.HttpStatusCode
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import org.springframework.web.client.RestClientException
import org.springframework.web.client.RestClientResponseException
import tools.jackson.databind.JsonNode
import tools.jackson.databind.ObjectMapper
import java.security.MessageDigest

@Component
class DifyWorkflowClient(
    restClientBuilder: RestClient.Builder,
    private val objectMapper: ObjectMapper,
    private val properties: HealthMindProperties,
) : DifyWorkflowPort {
    private val client = restClientBuilder.baseUrl(properties.dify.baseUrl.trimEnd('/')).build()

    override fun run(command: TaskExecution): DifyWorkflowResult {
        val apiKey = properties.dify.appKeys[command.difyAppId]
            ?: throw TaskExecutionException("DIFY_APP_KEY_MISSING", FailureCategory.PERMANENT, "Dify app key is not configured")
        val request = mapOf(
            "inputs" to mapOf(
                "task_id" to command.taskId.toString(),
                "attempt_id" to command.attemptId.toString(),
                "trace_id" to command.traceId,
            ),
            "response_mode" to "blocking",
            "user" to pseudonymousUser(command.taskId.toString()),
        )
        try {
            val response = client.post()
                .uri("/workflows/{workflowId}/run", command.difyWorkflowId)
                .header("Authorization", "Bearer $apiKey")
                .body(request)
                .retrieve()
                .body(JsonNode::class.java)
                ?: throw TaskExecutionException("DIFY_EMPTY_RESPONSE", FailureCategory.CONTRACT, "Dify returned an empty response")
            val data = response.path("data")
            val status = data.path("status").asString()
            if (status != "succeeded") {
                throw TaskExecutionException(
                    code = "DIFY_WORKFLOW_${status.uppercase()}",
                    category = if (status == "stopped") FailureCategory.CANCELLED else FailureCategory.PERMANENT,
                    message = data.path("error").asString("Dify workflow did not succeed").take(500),
                )
            }
            val returnedWorkflowId = data.path("workflow_id").asString(response.path("workflow_id").asString())
            if (returnedWorkflowId != command.difyWorkflowId) {
                throw TaskExecutionException("DIFY_WORKFLOW_VERSION_MISMATCH", FailureCategory.PERMANENT, "Dify returned a different workflow id")
            }
            val outputs = data.path("outputs")
            val resultNode = when {
                outputs.has("result") && outputs.path("result").isTextual -> objectMapper.readTree(outputs.path("result").asString())
                outputs.has("result") -> outputs.path("result")
                else -> outputs
            }
            return DifyWorkflowResult(
                workflowRunId = response.path("workflow_run_id").asString(data.path("id").asString()),
                workflowId = returnedWorkflowId,
                outputJson = objectMapper.writeValueAsString(resultNode),
                providerName = data.path("metadata").path("provider_name").takeUnless { it.isMissingNode }?.asString(),
                modelName = data.path("metadata").path("model_name").takeUnless { it.isMissingNode }?.asString(),
                modelVersion = command.difyWorkflowVersion,
                inputTokens = data.path("total_tokens").takeUnless { it.isMissingNode }?.asLong(),
            )
        } catch (exception: TaskExecutionException) {
            throw exception
        } catch (exception: RestClientResponseException) {
            throw classifyHttp(exception.statusCode, exception)
        } catch (exception: RestClientException) {
            throw TaskExecutionException("DIFY_NETWORK_ERROR", FailureCategory.TRANSIENT, "Dify request failed", exception)
        }
    }

    private fun classifyHttp(status: HttpStatusCode, cause: Throwable): TaskExecutionException = when {
        status.value() == 429 -> TaskExecutionException("DIFY_RATE_LIMITED", FailureCategory.TRANSIENT, "Dify rate limited the request", cause)
        status.is5xxServerError -> TaskExecutionException("DIFY_SERVER_ERROR", FailureCategory.TRANSIENT, "Dify server error", cause)
        status.value() == 401 || status.value() == 403 -> TaskExecutionException("DIFY_AUTH_FAILED", FailureCategory.PERMANENT, "Dify authentication failed", cause)
        status.value() == 404 -> TaskExecutionException("DIFY_WORKFLOW_NOT_FOUND", FailureCategory.PERMANENT, "Pinned Dify workflow was not found", cause)
        else -> TaskExecutionException("DIFY_REQUEST_REJECTED", FailureCategory.PERMANENT, "Dify rejected the request", cause)
    }

    private fun pseudonymousUser(taskId: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(taskId.toByteArray())
            .joinToString("") { "%02x".format(it) }
        return "hm-${digest.take(24)}"
    }
}
