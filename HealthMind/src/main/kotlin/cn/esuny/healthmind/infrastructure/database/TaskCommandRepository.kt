package cn.esuny.healthmind.infrastructure.database

import cn.esuny.contracts.integration.v1.IntegrationEvent
import cn.esuny.contracts.integration.v1.NutritionCaptureReadyPayload
import cn.esuny.contracts.integration.v1.NutritionEventTypes
import cn.esuny.healthmind.domain.task.AgentRunResult
import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.domain.task.TaskExecutionException
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import cn.esuny.healthmind.infrastructure.json.JsonSchemaService
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import org.springframework.stereotype.Repository
import org.springframework.transaction.annotation.Transactional
import tools.jackson.databind.JsonNode
import tools.jackson.databind.ObjectMapper
import java.sql.ResultSet
import java.sql.Timestamp
import java.time.Duration
import java.time.Instant
import java.util.UUID
import kotlin.math.min
import kotlin.random.Random

@Repository
class TaskCommandRepository(
    private val jdbc: NamedParameterJdbcTemplate,
    private val objectMapper: ObjectMapper,
    private val canonicalJson: CanonicalJson,
    private val schemas: JsonSchemaService,
    private val properties: HealthMindProperties,
) {
    @Transactional
    fun acceptCaptureReady(
        event: IntegrationEvent<NutritionCaptureReadyPayload>,
        eventNode: JsonNode,
        payloadDigest: String,
    ): UUID? {
        val inserted = jdbc.update(
            """
            INSERT INTO healthmind.integration_inbox
                (event_id, event_type, schema_version, producer, subject_id, aggregate_type, aggregate_id,
                 trace_id, payload_sha256, retention_until)
            VALUES (:eventId, :eventType, :schemaVersion, :producer, :subjectId, :aggregateType, :aggregateId,
                    :traceId, :payloadDigest, :retentionUntil)
            ON CONFLICT (event_id) DO NOTHING
            """.trimIndent(),
            mapOf(
                "eventId" to event.eventId,
                "eventType" to event.eventType,
                "schemaVersion" to event.schemaVersion,
                "producer" to event.producer,
                "subjectId" to event.subjectId,
                "aggregateType" to event.aggregateType,
                "aggregateId" to event.aggregateId,
                "traceId" to event.traceId,
                "payloadDigest" to payloadDigest,
                "retentionUntil" to Timestamp.from(Instant.now().plus(properties.retention.integration)),
            ),
        )
        if (inserted == 0) return null

        val release = jdbc.query(
            """
            SELECT tt.task_type_id, wr.release_id, wr.input_schema_version, wr.input_schema::text
              FROM healthmind.ai_task_types tt
              JOIN healthmind.workflow_releases wr ON wr.task_type_id = tt.task_type_id
             WHERE tt.task_type_code = 'nutrition.meal_analysis' AND tt.active AND wr.status = 'production'
            """.trimIndent(),
            emptyMap<String, Any>(),
        ) { rs, _ -> ProductionRelease(rs.getObject(1, UUID::class.java), rs.getObject(2, UUID::class.java), rs.getString(3), rs.getString(4)) }
            .singleOrNull()
            ?: throw cn.esuny.healthmind.domain.task.ProductionWorkflowUnavailableException()

        try {
            schemas.validate(release.inputSchema, eventNode, "INPUT_CONTRACT_INVALID")
        } catch (exception: cn.esuny.healthmind.domain.task.TaskExecutionException) {
            jdbc.update(
                """
                UPDATE healthmind.integration_inbox
                   SET status='failed', processed_at=NOW(), failure_code=:code,
                       failure_message='Input event failed the pinned release contract'
                 WHERE event_id=:eventId
                """.trimIndent(),
                mapOf("eventId" to event.eventId, "code" to exception.code),
            )
            return null
        }

        val taskId = UUID.randomUUID()
        val manifest = objectMapper.createObjectNode()
            .put("capture_session_id", event.payload.captureSessionId.toString())
            .put("meal_id", event.payload.mealId)
        jdbc.update(
            """
            INSERT INTO healthmind.ai_tasks
                (task_id, task_type_id, workflow_release_id, request_event_id, requester_service, subject_id,
                 aggregate_type, aggregate_id, idempotency_key, trace_id, input_schema_version, input_digest,
                 context_manifest, retention_until)
            VALUES (:taskId, :taskTypeId, :releaseId, :eventId, :requester, :subjectId,
                    :aggregateType, :aggregateId, :idempotencyKey, :traceId, :schemaVersion, :digest,
                    CAST(:manifest AS jsonb), :retentionUntil)
            """.trimIndent(),
            mapOf(
                "taskId" to taskId,
                "taskTypeId" to release.taskTypeId,
                "releaseId" to release.releaseId,
                "eventId" to event.eventId,
                "requester" to event.producer,
                "subjectId" to event.subjectId,
                "aggregateType" to event.aggregateType,
                "aggregateId" to event.aggregateId,
                "idempotencyKey" to event.eventId.toString(),
                "traceId" to event.traceId,
                "schemaVersion" to release.inputSchemaVersion,
                "digest" to payloadDigest,
                "manifest" to canonicalJson.stringify(manifest),
                "retentionUntil" to Timestamp.from(Instant.now().plus(properties.retention.audit)),
            ),
        )
        jdbc.update(
            "UPDATE healthmind.integration_inbox SET status='processed', processed_at=NOW() WHERE event_id=:eventId",
            mapOf("eventId" to event.eventId),
        )
        return taskId
    }

    @Transactional
    fun claimNext(): TaskExecution? {
        // Serialize the in-flight count and claim across HealthMind replicas.
        jdbc.query(
            "SELECT pg_advisory_xact_lock(hashtextextended('healthmind.agent.claim', 0))",
            emptyMap<String, Any>(),
        ) { _, _ -> Unit }
        val rows = jdbc.query(
            """
            SELECT t.task_id, t.lock_version, t.subject_id, t.aggregate_type, t.aggregate_id, t.trace_id,
                   (t.context_manifest->>'capture_session_id')::uuid AS capture_session_id,
                   (t.context_manifest->>'meal_id')::bigint AS meal_id,
                   wr.release_id, wr.agent_deployment_key, wr.agent_assistant_id, wr.agent_artifact_sha256,
                   wr.output_schema_version, wr.output_schema::text, wr.timeout_seconds, wr.max_attempts,
                   COALESCE((SELECT MAX(a.attempt_no) FROM healthmind.ai_task_attempts a WHERE a.task_id=t.task_id), 0) + 1 AS attempt_no
              FROM healthmind.ai_tasks t
              JOIN healthmind.workflow_releases wr ON wr.release_id=t.workflow_release_id
             WHERE t.status='queued' AND t.scheduled_at<=NOW() AND t.next_attempt_at<=NOW()
               AND (t.deadline_at IS NULL OR t.deadline_at>NOW())
               AND (SELECT COUNT(*) FROM healthmind.ai_task_attempts active
                     WHERE active.agent_managed AND active.status='running') < :maxInFlight
             ORDER BY t.priority DESC, t.scheduled_at, t.created_at
             FOR UPDATE OF t SKIP LOCKED
             LIMIT 1
            """.trimIndent(),
            mapOf("maxInFlight" to properties.agent.maxInFlight),
        ) { rs, _ -> rowToExecution(rs) }
        val selected = rows.singleOrNull() ?: return null
        val attemptId = UUID.randomUUID()
        val claimed = jdbc.update(
            """
            UPDATE healthmind.ai_tasks
               SET status='running', started_at=COALESCE(started_at,NOW()), lock_version=lock_version+1
             WHERE task_id=:taskId AND status='queued' AND lock_version=:lockVersion
            """.trimIndent(),
            mapOf("taskId" to selected.taskId, "lockVersion" to selected.lockVersion),
        )
        check(claimed == 1) { "Task claim lost optimistic lock" }
        jdbc.update(
            """
            INSERT INTO healthmind.ai_task_attempts
                (attempt_id, task_id, attempt_no, status, started_at, timeout_ms, agent_managed, agent_next_check_at)
            VALUES (:attemptId, :taskId, :attemptNo, 'running', NOW(), :timeoutMs, TRUE, NOW())
            """.trimIndent(),
            mapOf(
                "attemptId" to attemptId,
                "taskId" to selected.taskId,
                "attemptNo" to selected.attemptNo,
                "timeoutMs" to selected.timeoutSeconds * 1000,
            ),
        )
        return selected.copy(attemptId = attemptId, lockVersion = selected.lockVersion + 1)
    }

    @Transactional
    fun claimDue(): TaskExecution? {
        val rows = jdbc.query(
            """
            SELECT t.task_id, t.lock_version, t.subject_id, t.aggregate_type, t.aggregate_id, t.trace_id,
                   (t.context_manifest->>'capture_session_id')::uuid AS capture_session_id,
                   (t.context_manifest->>'meal_id')::bigint AS meal_id,
                   wr.release_id, wr.agent_deployment_key, wr.agent_assistant_id, wr.agent_artifact_sha256,
                   wr.output_schema_version, wr.output_schema::text, wr.timeout_seconds, wr.max_attempts,
                   a.attempt_id, a.attempt_no, a.agent_run_id
              FROM healthmind.ai_task_attempts a
              JOIN healthmind.ai_tasks t ON t.task_id=a.task_id
              JOIN healthmind.workflow_releases wr ON wr.release_id=t.workflow_release_id
             WHERE t.status='running' AND a.status='running' AND a.agent_managed AND a.agent_next_check_at<=NOW()
               AND a.started_at + (a.timeout_ms * INTERVAL '1 millisecond') >= NOW()
               AND a.attempt_no=(SELECT MAX(latest.attempt_no) FROM healthmind.ai_task_attempts latest WHERE latest.task_id=t.task_id)
             ORDER BY a.agent_next_check_at, a.created_at
             FOR UPDATE OF a SKIP LOCKED
             LIMIT 1
            """.trimIndent(),
            emptyMap<String, Any>(),
        ) { rs, _ -> rowToExecution(rs).copy(
            attemptId = rs.getObject("attempt_id", UUID::class.java),
            agentRunId = rs.getObject("agent_run_id", UUID::class.java),
        ) }
        val selected = rows.singleOrNull() ?: return null
        jdbc.update(
            "UPDATE healthmind.ai_task_attempts SET agent_next_check_at=:nextCheck WHERE attempt_id=:attemptId AND status='running'",
            mapOf(
                "attemptId" to selected.attemptId,
                "nextCheck" to Timestamp.from(Instant.now().plus(
                    maxOf(properties.agent.pollInterval,
                        properties.agent.readTimeout.multipliedBy(2).plus(properties.agent.connectTimeout).plus(Duration.ofSeconds(5))),
                )),
            ),
        )
        return selected
    }

    @Transactional
    fun attachRun(command: TaskExecution, runId: UUID) {
        val updated = jdbc.update(
            """
            UPDATE healthmind.ai_task_attempts
               SET agent_run_id=:runId, agent_next_check_at=NOW()
             WHERE attempt_id=:attemptId AND status='running' AND agent_run_id IS NULL
            """.trimIndent(),
            mapOf("attemptId" to command.attemptId, "runId" to runId),
        )
        check(updated == 1) { "Agent run could not be attached to the running attempt" }
    }

    @Transactional
    fun schedulePoll(command: TaskExecution) {
        jdbc.update(
            "UPDATE healthmind.ai_task_attempts SET agent_next_check_at=:nextCheck WHERE attempt_id=:attemptId AND status='running'",
            mapOf(
                "attemptId" to command.attemptId,
                "nextCheck" to Timestamp.from(Instant.now().plus(properties.agent.pollInterval)),
            ),
        )
    }

    @Transactional
    fun claimTimedOut(limit: Int = 100): List<TaskExecution> = jdbc.query(
        """
        SELECT t.task_id, t.lock_version, t.subject_id, t.aggregate_type, t.aggregate_id, t.trace_id,
               (t.context_manifest->>'capture_session_id')::uuid AS capture_session_id,
               (t.context_manifest->>'meal_id')::bigint AS meal_id,
               wr.release_id, wr.agent_deployment_key, wr.agent_assistant_id, wr.agent_artifact_sha256,
               wr.output_schema_version, wr.output_schema::text, wr.timeout_seconds, wr.max_attempts,
               a.attempt_id, a.attempt_no, a.agent_run_id
          FROM healthmind.ai_tasks t
          JOIN healthmind.workflow_releases wr ON wr.release_id=t.workflow_release_id
          JOIN healthmind.ai_task_attempts a ON a.task_id=t.task_id
         WHERE t.status='running' AND a.status='running' AND a.agent_managed
           AND a.started_at + (a.timeout_ms * INTERVAL '1 millisecond') < NOW()
           AND a.attempt_no=(SELECT MAX(latest.attempt_no) FROM healthmind.ai_task_attempts latest WHERE latest.task_id=t.task_id)
         ORDER BY a.started_at
         FOR UPDATE OF a SKIP LOCKED
         LIMIT :limit
        """.trimIndent(),
        mapOf("limit" to limit),
    ) { rs, _ -> rowToExecution(rs).copy(
        attemptId = rs.getObject("attempt_id", UUID::class.java),
        agentRunId = rs.getObject("agent_run_id", UUID::class.java),
    ) }

    @Transactional
    fun recoverTimedOut(): List<TaskExecution> {
        val expired = claimTimedOut()
        expired.forEach { command ->
            fail(
                command,
                TaskExecutionException("ATTEMPT_TIMEOUT", FailureCategory.TIMEOUT, "Execution exceeded configured timeout"),
                FailureCategory.TIMEOUT,
                "ATTEMPT_TIMEOUT",
            )
        }
        return expired
    }

    @Transactional
    fun complete(command: TaskExecution, result: AgentRunResult, resultNode: JsonNode) {
        val digest = canonicalJson.sha256(resultNode)
        val resultId = UUID.randomUUID()
        val eventId = UUID.randomUUID()
        val confidence = resultNode.path("overall_confidence").takeUnless { it.isMissingNode || it.isNull }?.decimalValue()
        val attemptCompleted = jdbc.update(
            """
            UPDATE healthmind.ai_task_attempts SET status='succeeded', agent_run_id=:runId,
                   provider_name=:provider, model_name=:model, model_version=:modelVersion,
                   finished_at=NOW(), duration_ms=GREATEST(0, EXTRACT(EPOCH FROM (NOW()-started_at))*1000)::bigint,
                   input_tokens=:inputTokens, output_tokens=:outputTokens
             WHERE attempt_id=:attemptId AND status='running'
            """.trimIndent(),
            mapOf(
                "attemptId" to command.attemptId,
                "runId" to result.runId,
                "provider" to result.providerName,
                "model" to result.modelName,
                "modelVersion" to result.modelVersion,
                "inputTokens" to result.inputTokens,
                "outputTokens" to result.outputTokens,
            ),
        )
        check(attemptCompleted == 1) { "Attempt completion lost its running state" }
        jdbc.update(
            """
            INSERT INTO healthmind.ai_task_results
                (result_id, task_id, output_schema_version, result_payload, result_sha256, confidence, produced_at, expires_at)
            VALUES (:resultId, :taskId, :schemaVersion, CAST(:payload AS jsonb), :digest, :confidence, NOW(), :expiresAt)
            """.trimIndent(),
            mapOf(
                "resultId" to resultId,
                "taskId" to command.taskId,
                "schemaVersion" to command.outputSchemaVersion,
                "payload" to canonicalJson.stringify(resultNode),
                "digest" to digest,
                "confidence" to confidence,
                "expiresAt" to Timestamp.from(Instant.now().plus(properties.retention.result)),
            ),
        )
        val completed = jdbc.update(
            """
            UPDATE healthmind.ai_tasks SET status='succeeded', completed_at=NOW(), lock_version=lock_version+1
             WHERE task_id=:taskId AND status='running' AND lock_version=:lockVersion
            """.trimIndent(),
            mapOf("taskId" to command.taskId, "lockVersion" to command.lockVersion),
        )
        check(completed == 1) { "Task completion lost optimistic lock" }
        val eventPayload = completionEnvelope(command, resultNode, eventId)
        insertOutbox(command, eventId, NutritionEventTypes.ANALYSIS_COMPLETED, properties.kafka.analysisCompletedDestination, eventPayload)
    }

    @Transactional
    fun fail(command: TaskExecution, failure: Throwable, category: FailureCategory, code: String) {
        val sanitized = failure.message?.take(500) ?: code
        val attemptFailed = jdbc.update(
            """
            UPDATE healthmind.ai_task_attempts
               SET status=:status, finished_at=NOW(), failure_category=:category, failure_code=:code,
                   failure_message=:message,
                   duration_ms=GREATEST(0, EXTRACT(EPOCH FROM (NOW()-started_at))*1000)::bigint
             WHERE attempt_id=:attemptId AND status='running'
            """.trimIndent(),
            mapOf(
                "attemptId" to command.attemptId,
                "status" to if (category == FailureCategory.TIMEOUT) "timed_out" else "failed",
                "category" to category.wireValue,
                "code" to code,
                "message" to sanitized,
            ),
        )
        check(attemptFailed == 1) { "Attempt failure lost its running state" }
        if (category.retryable && command.attemptNo < command.maxAttempts) {
            val baseSeconds = min(20, 5 shl (command.attemptNo - 1))
            val jitterMillis = Random.nextLong(0, 1000)
            val retried = jdbc.update(
                """
                UPDATE healthmind.ai_tasks
                   SET status='queued', next_attempt_at=:nextAttempt, failure_code=NULL, failure_message=NULL,
                       lock_version=lock_version+1
                 WHERE task_id=:taskId AND status='running' AND lock_version=:lockVersion
                """.trimIndent(),
                mapOf(
                    "taskId" to command.taskId,
                    "lockVersion" to command.lockVersion,
                    "nextAttempt" to Timestamp.from(Instant.now().plusSeconds(baseSeconds.toLong()).plusMillis(jitterMillis)),
                ),
            )
            check(retried == 1) { "Task retry lost optimistic lock" }
            return
        }
        val failed = jdbc.update(
            """
            UPDATE healthmind.ai_tasks
               SET status='failed', completed_at=NOW(), failure_code=:code, failure_message=:message,
                   lock_version=lock_version+1
             WHERE task_id=:taskId AND status='running' AND lock_version=:lockVersion
            """.trimIndent(),
            mapOf("taskId" to command.taskId, "lockVersion" to command.lockVersion, "code" to code, "message" to sanitized),
        )
        check(failed == 1) { "Task failure lost optimistic lock" }
        val eventId = UUID.randomUUID()
        val node = objectMapper.createObjectNode()
            .put("event_id", eventId.toString())
            .put("event_type", NutritionEventTypes.ANALYSIS_FAILED)
            .put("occurred_at", Instant.now().toString())
            .put("producer", "HealthMind")
            .put("trace_id", command.traceId)
            .put("subject_id", command.subjectId?.toString())
            .put("aggregate_type", command.aggregateType)
            .put("aggregate_id", command.aggregateId)
            .put("schema_version", NutritionEventTypes.SCHEMA_VERSION)
        node.set("payload", objectMapper.createObjectNode()
            .put("task_id", command.taskId.toString())
            .put("capture_session_id", command.captureSessionId.toString())
            .put("meal_id", command.mealId)
            .put("error_code", code)
            .put("failure_category", category.wireValue)
            .put("retryable", category.retryable)
            .put("error_summary", sanitized))
        insertOutbox(command, eventId, NutritionEventTypes.ANALYSIS_FAILED, properties.kafka.analysisFailedDestination, node)
    }

    private fun completionEnvelope(command: TaskExecution, resultNode: JsonNode, eventId: UUID): JsonNode {
        val node = objectMapper.createObjectNode()
            .put("event_id", eventId.toString())
            .put("event_type", NutritionEventTypes.ANALYSIS_COMPLETED)
            .put("occurred_at", Instant.now().toString())
            .put("producer", "HealthMind")
            .put("trace_id", command.traceId)
            .put("subject_id", command.subjectId?.toString())
            .put("aggregate_type", command.aggregateType)
            .put("aggregate_id", command.aggregateId)
            .put("schema_version", NutritionEventTypes.SCHEMA_VERSION)
        val payload = resultNode.deepCopy() as tools.jackson.databind.node.ObjectNode
        payload.put("task_id", command.taskId.toString())
            .put("capture_session_id", command.captureSessionId.toString())
            .put("meal_id", command.mealId)
            .put("result_version", 1)
        node.set("payload", payload)
        return node
    }

    private fun insertOutbox(command: TaskExecution, eventId: UUID, type: String, destination: String, payload: JsonNode) {
        val json = canonicalJson.stringify(payload)
        jdbc.update(
            """
            INSERT INTO healthmind.integration_outbox
                (event_id, task_id, event_type, schema_version, aggregate_type, aggregate_id,
                 destination_key, partition_key, payload, payload_sha256, trace_id, retention_until)
            VALUES (:eventId, :taskId, :eventType, :schemaVersion, :aggregateType, :aggregateId,
                    :destination, :partitionKey, CAST(:payload AS jsonb), :digest, :traceId, :retentionUntil)
            """.trimIndent(),
            mapOf(
                "eventId" to eventId,
                "taskId" to command.taskId,
                "eventType" to type,
                "schemaVersion" to NutritionEventTypes.SCHEMA_VERSION,
                "aggregateType" to command.aggregateType,
                "aggregateId" to command.aggregateId,
                "destination" to destination,
                "partitionKey" to command.captureSessionId.toString(),
                "payload" to json,
                "digest" to canonicalJson.sha256(payload),
                "traceId" to command.traceId,
                "retentionUntil" to Timestamp.from(Instant.now().plus(properties.retention.integration)),
            ),
        )
    }

    private fun rowToExecution(rs: ResultSet): TaskExecution = TaskExecution(
        taskId = rs.getObject("task_id", UUID::class.java),
        attemptId = UUID(0, 0),
        attemptNo = rs.getInt("attempt_no"),
        maxAttempts = rs.getInt("max_attempts"),
        lockVersion = rs.getLong("lock_version"),
        subjectId = rs.getObject("subject_id", UUID::class.java),
        aggregateType = rs.getString("aggregate_type"),
        aggregateId = rs.getString("aggregate_id"),
        captureSessionId = rs.getObject("capture_session_id", UUID::class.java),
        mealId = rs.getLong("meal_id"),
        traceId = rs.getString("trace_id"),
        releaseId = rs.getObject("release_id", UUID::class.java),
        agentDeploymentKey = rs.getString("agent_deployment_key"),
        agentAssistantId = rs.getString("agent_assistant_id"),
        agentArtifactSha256 = rs.getString("agent_artifact_sha256"),
        outputSchemaVersion = rs.getString("output_schema_version"),
        outputSchema = rs.getString("output_schema"),
        timeoutSeconds = rs.getInt("timeout_seconds"),
    )

    private data class ProductionRelease(
        val taskTypeId: UUID,
        val releaseId: UUID,
        val inputSchemaVersion: String,
        val inputSchema: String,
    )
}
