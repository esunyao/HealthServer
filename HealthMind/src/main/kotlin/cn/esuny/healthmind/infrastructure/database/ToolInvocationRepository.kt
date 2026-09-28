package cn.esuny.healthmind.infrastructure.database

import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import org.springframework.stereotype.Repository
import org.springframework.transaction.annotation.Transactional
import java.sql.Timestamp
import java.time.Instant
import java.util.UUID

@Repository
class ToolInvocationRepository(
    private val jdbc: NamedParameterJdbcTemplate,
    private val canonicalJson: CanonicalJson,
) {
    @Transactional
    fun authorizeAndStart(
        toolCode: String,
        taskId: UUID,
        attemptId: UUID,
        toolCallId: String,
        request: tools.jackson.databind.JsonNode,
        callerSubjectId: UUID?,
        callerScopes: Set<String>,
    ): StartedInvocation {
        require(toolCallId.isNotBlank() && toolCallId.length <= 128) { "Invalid tool_call_id" }
        runCatching { UUID.fromString(toolCallId) }
            .getOrElse { throw ToolAccessException("TOOL_CALL_ID_INVALID", "tool_call_id must be a UUID") }
        val requestSha = canonicalJson.sha256(request)
        val grants = jdbc.query(
            """
            SELECT t.task_id, tt.task_type_code, t.subject_id, t.trace_id, t.workflow_release_id,
                   t.context_manifest::text context_manifest,
                   rt.tool_id, rt.request_schema_version, rt.response_schema_version,
                   rt.request_schema::text, rt.response_schema::text, rt.allowed_scope, rt.max_calls,
                   (SELECT COUNT(*) FROM healthmind.ai_tool_invocations i
                     WHERE i.attempt_id=:attemptId AND i.tool_id=rt.tool_id AND i.status <> 'denied') call_count
              FROM healthmind.ai_tasks t
              JOIN healthmind.ai_task_types tt ON tt.task_type_id=t.task_type_id
              JOIN healthmind.ai_task_attempts a ON a.task_id=t.task_id AND a.attempt_id=:attemptId
              JOIN healthmind.workflow_release_tools rt ON rt.release_id=t.workflow_release_id
              JOIN healthmind.ai_tool_definitions d ON d.tool_id=rt.tool_id AND d.active
             WHERE t.task_id=:taskId AND t.status='running' AND a.status='running'
               AND d.tool_code=:toolCode
             FOR UPDATE OF a
            """.trimIndent(),
            mapOf("taskId" to taskId, "attemptId" to attemptId, "toolCode" to toolCode),
        ) { rs, _ ->
            ToolGrant(
                taskId = rs.getObject("task_id", UUID::class.java),
                attemptId = attemptId,
                taskTypeCode = rs.getString("task_type_code"),
                subjectId = rs.getObject("subject_id", UUID::class.java),
                traceId = rs.getString("trace_id"),
                releaseId = rs.getObject("workflow_release_id", UUID::class.java),
                contextManifest = rs.getString("context_manifest"),
                toolId = rs.getObject("tool_id", UUID::class.java),
                requestSchemaVersion = rs.getString("request_schema_version"),
                responseSchemaVersion = rs.getString("response_schema_version"),
                requestSchema = rs.getString("request_schema"),
                responseSchema = rs.getString("response_schema"),
                allowedScope = rs.getString("allowed_scope"),
                maxCalls = rs.getInt("max_calls"),
                callCount = rs.getInt("call_count"),
            )
        }
        val grant = grants.singleOrNull() ?: throw ToolAccessException("TOOL_NOT_ALLOWED", "Tool is not enabled for this task release")
        if (!callerScopes.contains(grant.allowedScope)) throw ToolAccessException("TOOL_SCOPE_DENIED", "Required tool scope is missing")

        val existing = jdbc.query(
            """SELECT invocation_id, request_sha256, status
                 FROM healthmind.ai_tool_invocations
                WHERE attempt_id=:attemptId AND tool_id=:toolId AND tool_call_id=:toolCallId
                FOR UPDATE""",
            mapOf("attemptId" to attemptId, "toolId" to grant.toolId, "toolCallId" to toolCallId),
        ) { rs, _ -> ExistingInvocation(
            rs.getObject("invocation_id", UUID::class.java),
            rs.getString("request_sha256"),
            rs.getString("status"),
        ) }.singleOrNull()
        if (existing != null) {
            if (existing.requestSha != requestSha) {
                throw ToolAccessException("TOOL_IDEMPOTENCY_CONFLICT", "tool_call_id was reused with different arguments")
            }
            if (existing.status == "denied") {
                throw ToolAccessException("TOOL_NOT_ALLOWED", "Previous call with this tool_call_id was denied")
            }
            if (existing.status == "running") {
                throw ToolAccessException("TOOL_CALL_IN_PROGRESS", "The same tool_call_id is already being processed")
            }
            jdbc.update(
                """UPDATE healthmind.ai_tool_invocations
                      SET replay_count=replay_count+1, last_replayed_at=NOW()
                    WHERE invocation_id=:invocationId""",
                mapOf("invocationId" to existing.invocationId),
            )
            return StartedInvocation(existing.invocationId, grant, isReplay = true)
        }
        if (grant.callCount >= grant.maxCalls) throw ToolAccessException("TOOL_CALL_LIMIT_EXCEEDED", "Tool call limit exceeded")
        val invocationId = UUID.randomUUID()
        jdbc.update(
            """
            INSERT INTO healthmind.ai_tool_invocations
                (invocation_id, task_id, attempt_id, release_id, tool_id, tool_call_id, idempotency_key,
                 caller_subject_id, authorized_scope, status, request_schema_version, request_sha256,
                 started_at, trace_id)
            VALUES (:invocationId, :taskId, :attemptId, :releaseId, :toolId, :toolCallId, :idempotencyKey,
                    :callerSubjectId, :scope, 'running', :schemaVersion, :requestSha, NOW(), :traceId)
            """.trimIndent(),
            mapOf(
                "invocationId" to invocationId,
                "taskId" to taskId,
                "attemptId" to attemptId,
                "releaseId" to grant.releaseId,
                "toolId" to grant.toolId,
                "toolCallId" to toolCallId,
                "idempotencyKey" to toolCallId,
                "callerSubjectId" to callerSubjectId,
                "scope" to grant.allowedScope,
                "schemaVersion" to grant.requestSchemaVersion,
                "requestSha" to requestSha,
                "traceId" to grant.traceId,
            ),
        )
        return StartedInvocation(invocationId, grant, isReplay = false)
    }

    @Transactional
    fun succeed(invocation: StartedInvocation, responseSha: String) {
        jdbc.update(
            """
            UPDATE healthmind.ai_tool_invocations SET status='succeeded', response_schema_version=:schemaVersion,
                   response_sha256=:responseSha, completed_at=NOW(),
                   failure_code=NULL, failure_message=NULL,
                   duration_ms=GREATEST(0, EXTRACT(EPOCH FROM (NOW()-started_at))*1000)::bigint
             WHERE invocation_id=:invocationId AND status IN ('running','failed','succeeded')
            """.trimIndent(),
            mapOf(
                "invocationId" to invocation.invocationId,
                "schemaVersion" to invocation.grant.responseSchemaVersion,
                "responseSha" to responseSha,
            ),
        )
    }

    @Transactional
    fun fail(invocation: StartedInvocation, code: String) {
        jdbc.update(
            """
            UPDATE healthmind.ai_tool_invocations SET status='failed', failure_code=:code,
                   failure_message='Internal tool invocation failed', completed_at=NOW(),
                   duration_ms=GREATEST(0, EXTRACT(EPOCH FROM (NOW()-started_at))*1000)::bigint
             WHERE invocation_id=:invocationId AND status IN ('running','failed')
            """.trimIndent(),
            mapOf("invocationId" to invocation.invocationId, "code" to code),
        )
    }

    data class ToolGrant(
        val taskId: UUID,
        val attemptId: UUID,
        val taskTypeCode: String,
        val subjectId: UUID?,
        val traceId: String,
        val releaseId: UUID,
        val contextManifest: String,
        val toolId: UUID,
        val requestSchemaVersion: String,
        val responseSchemaVersion: String,
        val requestSchema: String,
        val responseSchema: String,
        val allowedScope: String,
        val maxCalls: Int,
        val callCount: Int,
    )

    data class StartedInvocation(val invocationId: UUID, val grant: ToolGrant, val isReplay: Boolean)

    private data class ExistingInvocation(val invocationId: UUID, val requestSha: String, val status: String)
}

class ToolAccessException(val code: String, message: String) : RuntimeException(message)
