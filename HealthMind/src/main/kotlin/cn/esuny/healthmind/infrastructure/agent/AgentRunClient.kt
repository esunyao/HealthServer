package cn.esuny.healthmind.infrastructure.agent

import cn.esuny.healthmind.application.port.out.AgentRunPort
import cn.esuny.healthmind.application.port.out.AgentRunState
import cn.esuny.healthmind.domain.task.AgentRunResult
import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.domain.task.TaskExecutionException
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.oauth.ClientCredentialsTokenProvider
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.http.HttpStatusCode
import org.springframework.http.client.JdkClientHttpRequestFactory
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import org.springframework.web.client.RestClientException
import org.springframework.web.client.RestClientResponseException
import tools.jackson.databind.JsonNode
import tools.jackson.databind.ObjectMapper
import java.net.URI
import java.net.http.HttpClient
import java.util.UUID

@Component
class AgentRunClient(
    @Qualifier("directRestClientBuilder") private val builder: RestClient.Builder,
    private val objectMapper: ObjectMapper,
    private val tokens: ClientCredentialsTokenProvider,
    private val properties: HealthMindProperties,
) : AgentRunPort {
    private val clients = properties.agent.deployments.mapValues { (_, address) ->
        val uri = URI.create(address)
        require(uri.host != null && uri.userInfo == null && uri.rawQuery == null && uri.rawFragment == null &&
            (uri.path.isNullOrEmpty() || uri.path == "/") &&
            (uri.scheme == "https" || (uri.scheme == "http" && uri.host in setOf("localhost", "127.0.0.1")))) {
            "Agent deployment must use HTTPS or loopback HTTP"
        }
        val httpClient = HttpClient.newBuilder().connectTimeout(properties.agent.connectTimeout).build()
        builder.clone()
            .requestFactory(JdkClientHttpRequestFactory(httpClient).apply { setReadTimeout(properties.agent.readTimeout) })
            .baseUrl(address.trimEnd('/'))
            .build()
    }

    override fun start(command: TaskExecution): UUID {
        val request = mapOf(
            "assistant_id" to command.agentAssistantId,
            "input" to mapOf(
                "task_id" to command.taskId.toString(),
                "attempt_id" to command.attemptId.toString(),
                "trace_id" to command.traceId,
            ),
            "metadata" to mapOf(
                "task_id" to command.taskId.toString(),
                "attempt_id" to command.attemptId.toString(),
                "release_id" to command.releaseId.toString(),
                "artifact_sha256" to command.agentArtifactSha256,
            ),
            "on_completion" to "keep",
        )
        val response = request(command) { client, bearer ->
            client.post().uri("/runs")
                .header("Authorization", "Bearer $bearer")
                .header("Idempotency-Key", command.attemptId.toString())
                .body(request).retrieve().body(JsonNode::class.java)
        }
        verifyRunIdentity(response, command)
        return parseRunId(response)
    }

    override fun inspect(command: TaskExecution): AgentRunState {
        val runId = requireNotNull(command.agentRunId)
        val run = request(command) { client, bearer ->
            client.get().uri("/runs/{runId}", runId)
                .header("Authorization", "Bearer $bearer")
                .retrieve().body(JsonNode::class.java)
        } ?: throw TaskExecutionException("AGENT_EMPTY_RESPONSE", FailureCategory.CONTRACT, "Agent returned no run status")
        verifyRunIdentity(run, command)
        if (parseRunId(run) != runId) {
            throw TaskExecutionException("AGENT_RUN_MISMATCH", FailureCategory.CONTRACT, "Agent returned another run")
        }
        return when (run.path("status").asString()) {
            "pending", "running" -> AgentRunState.Active
            "success" -> {
                val response = request(command) { client, bearer ->
                    client.get().uri("/runs/{runId}/wait", runId)
                        .header("Authorization", "Bearer $bearer")
                        .retrieve().body(JsonNode::class.java)
                }
                val output = response?.path("output")
                if (output == null || !output.isObject) {
                    throw TaskExecutionException("AGENT_OUTPUT_INVALID", FailureCategory.CONTRACT, "Agent output must be an object")
                }
                AgentRunState.Succeeded(AgentRunResult(runId, objectMapper.writeValueAsString(output)))
            }
            "error" -> AgentRunState.Failed("AGENT_RUN_FAILED", FailureCategory.PERMANENT, "Agent run failed")
            "interrupted" -> AgentRunState.Failed("AGENT_RUN_INTERRUPTED", FailureCategory.CANCELLED, "Agent run was interrupted")
            else -> throw TaskExecutionException("AGENT_STATUS_INVALID", FailureCategory.CONTRACT, "Agent returned an unknown run status")
        }
    }

    override fun cancel(command: TaskExecution) {
        val runId = command.agentRunId ?: return
        request(command) { client, bearer ->
            client.post().uri("/runs/{runId}/cancel", runId)
                .header("Authorization", "Bearer $bearer")
                .retrieve().toBodilessEntity()
            null
        }
    }

    private fun client(command: TaskExecution): RestClient = clients[command.agentDeploymentKey]
        ?: throw TaskExecutionException("AGENT_DEPLOYMENT_MISSING", FailureCategory.PERMANENT, "Pinned agent deployment is not configured")

    private fun parseRunId(response: JsonNode?): UUID = try {
        UUID.fromString(response?.path("run_id")?.asString())
    } catch (_: Exception) {
        throw TaskExecutionException("AGENT_RUN_ID_INVALID", FailureCategory.CONTRACT, "Agent returned no valid run ID")
    }

    private fun verifyRunIdentity(response: JsonNode?, command: TaskExecution) {
        val metadata = response?.path("metadata")
            ?: throw TaskExecutionException("AGENT_IDENTITY_MISMATCH", FailureCategory.CONTRACT, "Agent returned no run identity")
        if (response.path("assistant_id").asString() != command.agentAssistantId ||
            metadata.path("task_id").asString() != command.taskId.toString() ||
            metadata.path("attempt_id").asString() != command.attemptId.toString() ||
            metadata.path("release_id").asString() != command.releaseId.toString() ||
            metadata.path("artifact_sha256").asString() != command.agentArtifactSha256
        ) {
            throw TaskExecutionException("AGENT_IDENTITY_MISMATCH", FailureCategory.CONTRACT, "Agent run identity does not match the pinned release")
        }
    }

    private fun <T> request(command: TaskExecution, action: (RestClient, String) -> T): T = try {
        action(client(command), tokens.token(properties.oauth.agent))
    } catch (exception: TaskExecutionException) {
        throw exception
    } catch (exception: RestClientResponseException) {
        throw classifyHttp(exception.statusCode, exception)
    } catch (exception: RestClientException) {
        throw TaskExecutionException("AGENT_UNAVAILABLE", FailureCategory.TRANSIENT, "Agent service is unavailable", exception)
    }

    private fun classifyHttp(status: HttpStatusCode, cause: Throwable): TaskExecutionException = when {
        status.value() == 429 || status.is5xxServerError ->
            TaskExecutionException("AGENT_UNAVAILABLE", FailureCategory.TRANSIENT, "Agent service is unavailable", cause)
        status.value() == 401 || status.value() == 403 ->
            TaskExecutionException("AGENT_AUTH_FAILED", FailureCategory.PERMANENT, "Agent authentication failed", cause)
        status.value() == 404 ->
            TaskExecutionException("AGENT_RESOURCE_MISSING", FailureCategory.PERMANENT, "Pinned agent or run was not found", cause)
        else -> TaskExecutionException("AGENT_REQUEST_REJECTED", FailureCategory.PERMANENT, "Agent rejected the request", cause)
    }
}
