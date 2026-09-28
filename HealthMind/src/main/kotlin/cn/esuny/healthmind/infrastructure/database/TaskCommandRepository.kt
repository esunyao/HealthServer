package cn.esuny.healthmind.infrastructure.database

import cn.esuny.contracts.integration.v1.IntegrationEvent
import cn.esuny.healthmind.domain.task.AgentRunResult
import cn.esuny.healthmind.domain.task.AgentSubmissionState
import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.domain.task.TaskExecutionException
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import cn.esuny.healthmind.infrastructure.json.JsonSchemaService
import cn.esuny.healthmind.application.port.out.TaskOutboxMessage
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import org.springframework.stereotype.Repository
import org.springframework.transaction.annotation.Transactional
import tools.jackson.databind.JsonNode
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
    private val canonicalJson: CanonicalJson,
    private val schemas: JsonSchemaService,
    private val properties: HealthMindProperties,
) {
    private val workerId = UUID.randomUUID().toString()

    @Transactional
    fun accept(
        event: IntegrationEvent<*>,
        eventNode: JsonNode,
        payloadDigest: String,
        taskTypeCode: String,
        contextManifest: String,
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
        if (inserted == 0) {
            val existingDigest = jdbc.query(
                "SELECT payload_sha256 FROM healthmind.integration_inbox WHERE event_id=:eventId",
                mapOf("eventId" to event.eventId),
            ) { rs, _ -> rs.getString("payload_sha256") }.singleOrNull()
            if (existingDigest != payloadDigest) {
                throw TaskExecutionException(
                    "EVENT_IDEMPOTENCY_CONFLICT",
                    FailureCategory.CONTRACT,
                    "Integration event ID was reused with different content",
                )
            }
            return null
        }

        val release = jdbc.query(
            """
            SELECT tt.task_type_id, wr.release_id, wr.input_schema_version, wr.input_schema::text
              FROM healthmind.ai_task_types tt
              JOIN healthmind.workflow_releases wr ON wr.task_type_id = tt.task_type_id
             WHERE tt.task_type_code = :taskTypeCode AND tt.active AND wr.status = 'production'
            """.trimIndent(),
            mapOf("taskTypeCode" to taskTypeCode),
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
                "manifest" to contextManifest,
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
            SELECT t.task_id, t.lock_version, tt.task_type_code, t.subject_id, t.aggregate_type, t.aggregate_id,
                   t.context_manifest::text AS context_manifest, t.trace_id,
                   NULL::varchar AS lease_owner, 0::bigint AS lease_version,
                   wr.release_id, wr.agent_deployment_key, wr.agent_assistant_id, wr.agent_artifact_sha256,
                   wr.output_schema_version, wr.output_schema::text, wr.timeout_seconds, wr.max_attempts,
                   COALESCE((SELECT MAX(a.attempt_no) FROM healthmind.ai_task_attempts a WHERE a.task_id=t.task_id), 0) + 1 AS attempt_no
              FROM healthmind.ai_tasks t
              JOIN healthmind.ai_task_types tt ON tt.task_type_id=t.task_type_id
              JOIN healthmind.workflow_releases wr ON wr.release_id=t.workflow_release_id
             WHERE t.status='queued' AND t.scheduled_at<=NOW() AND t.next_attempt_at<=NOW()
               AND (t.deadline_at IS NULL OR t.deadline_at>NOW())
               AND NOT EXISTS (SELECT 1 FROM healthmind.ai_task_attempts active
                                WHERE active.task_id=t.task_id AND active.status IN ('pending','running'))
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
                (attempt_id, task_id, workflow_release_id, attempt_no, status, started_at, timeout_ms,
                 agent_managed, agent_next_check_at)
            VALUES (:attemptId, :taskId, :releaseId, :attemptNo, 'running', NOW(), :timeoutMs, TRUE, NOW())
            """.trimIndent(),
            mapOf(
                "attemptId" to attemptId,
                "taskId" to selected.taskId,
                "releaseId" to selected.releaseId,
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
            SELECT t.task_id, t.lock_version, tt.task_type_code, t.subject_id, t.aggregate_type, t.aggregate_id,
                   t.context_manifest::text AS context_manifest, t.trace_id,
                   wr.release_id, wr.agent_deployment_key, wr.agent_assistant_id, wr.agent_artifact_sha256,
                   wr.output_schema_version, wr.output_schema::text, wr.timeout_seconds, wr.max_attempts,
                   a.attempt_id, a.attempt_no, a.agent_run_id, a.agent_submission_state,
                   a.lease_owner, a.lease_version
              FROM healthmind.ai_task_attempts a
              JOIN healthmind.ai_tasks t ON t.task_id=a.task_id
              JOIN healthmind.ai_task_types tt ON tt.task_type_id=t.task_type_id
              JOIN healthmind.workflow_releases wr ON wr.release_id=t.workflow_release_id
             WHERE t.status='running' AND a.status='running' AND a.agent_managed AND a.agent_next_check_at<=NOW()
               AND (a.lease_expires_at IS NULL OR a.lease_expires_at<=NOW())
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
            agentSubmissionState = AgentSubmissionState.valueOf(rs.getString("agent_submission_state").uppercase()),
            leaseOwner = rs.getString("lease_owner") ?: "",
            leaseVersion = rs.getLong("lease_version"),
        ) }
        val selected = rows.singleOrNull() ?: return null
        val leaseDuration = maxOf(
            properties.agent.pollInterval,
            properties.agent.readTimeout.multipliedBy(2)
                .plus(properties.agent.connectTimeout)
                .plus(Duration.ofSeconds(5)),
        )
        val leased = jdbc.update(
            """UPDATE healthmind.ai_task_attempts
                  SET agent_next_check_at=:nextCheck,
                      lease_owner=:leaseOwner,
                      lease_expires_at=:leaseExpiresAt,
                      lease_version=lease_version+1,
                      agent_submission_state=CASE WHEN agent_submission_state='new' THEN 'submitting' ELSE agent_submission_state END
                WHERE attempt_id=:attemptId AND status='running' AND lease_version=:leaseVersion""",
            mapOf(
                "attemptId" to selected.attemptId,
                "leaseOwner" to workerId,
                "leaseVersion" to selected.leaseVersion,
                "leaseExpiresAt" to Timestamp.from(Instant.now().plus(leaseDuration)),
                "nextCheck" to Timestamp.from(Instant.now().plus(leaseDuration)),
            ),
        )
        check(leased == 1) { "Agent attempt lease was lost before processing" }
        return selected.copy(leaseOwner = workerId, leaseVersion = selected.leaseVersion + 1)
    }

    @Transactional
    fun attachRun(command: TaskExecution, runId: UUID) {
        val updated = jdbc.update(
            """
            UPDATE healthmind.ai_task_attempts
               SET agent_run_id=:runId, agent_submission_state='attached', agent_next_check_at=NOW(),
                   lease_owner=NULL, lease_expires_at=NULL, lease_version=lease_version+1
             WHERE attempt_id=:attemptId AND status='running' AND lease_owner=:leaseOwner
               AND lease_version=:leaseVersion AND (agent_run_id IS NULL OR agent_run_id=:runId)
            """.trimIndent(),
            mapOf(
                "attemptId" to command.attemptId,
                "runId" to runId,
                "leaseOwner" to command.leaseOwner,
                "leaseVersion" to command.leaseVersion,
            ),
        )
        check(updated == 1) { "Agent run could not be attached to the running attempt" }
    }

    @Transactional
    fun markSubmissionUnknown(command: TaskExecution) {
        val updated = jdbc.update(
            """UPDATE healthmind.ai_task_attempts
                  SET agent_submission_state='uncertain', agent_next_check_at=:nextCheck,
                      lease_owner=NULL, lease_expires_at=NULL, lease_version=lease_version+1
                WHERE attempt_id=:attemptId AND status='running' AND agent_run_id IS NULL
                  AND lease_owner=:leaseOwner AND lease_version=:leaseVersion""",
            mapOf("attemptId" to command.attemptId,
                "nextCheck" to Timestamp.from(Instant.now().plus(properties.agent.pollInterval)),
                "leaseOwner" to command.leaseOwner,
                "leaseVersion" to command.leaseVersion),
        )
        check(updated == 1) { "Agent submission lease was lost before marking uncertainty" }
    }

    @Transactional
    fun resetSubmission(command: TaskExecution) {
        val updated = jdbc.update(
            """UPDATE healthmind.ai_task_attempts
                  SET agent_submission_state='new', agent_next_check_at=:nextCheck,
                      lease_owner=NULL, lease_expires_at=NULL, lease_version=lease_version+1
                WHERE attempt_id=:attemptId AND status='running'
                  AND agent_run_id IS NULL AND agent_submission_state='submitting'
                  AND lease_owner=:leaseOwner AND lease_version=:leaseVersion""",
            mapOf("attemptId" to command.attemptId,
                "nextCheck" to Timestamp.from(Instant.now().plus(properties.agent.pollInterval)),
                "leaseOwner" to command.leaseOwner,
                "leaseVersion" to command.leaseVersion),
        )
        check(updated == 1) { "Agent submission lease was lost before resetting submission" }
    }

    @Transactional
    fun schedulePoll(command: TaskExecution) {
        val released = jdbc.update(
            """UPDATE healthmind.ai_task_attempts
                  SET agent_next_check_at=:nextCheck, lease_owner=NULL, lease_expires_at=NULL,
                      lease_version=lease_version+1
                WHERE attempt_id=:attemptId AND status='running'
                  AND lease_owner=:leaseOwner AND lease_version=:leaseVersion""",
            mapOf(
                "attemptId" to command.attemptId,
                "nextCheck" to Timestamp.from(Instant.now().plus(properties.agent.pollInterval)),
                "leaseOwner" to command.leaseOwner,
                "leaseVersion" to command.leaseVersion,
            ),
        )
        check(released == 1) { "Agent attempt lease was lost while scheduling the next check" }
    }

    @Transactional
    fun claimTimedOut(limit: Int = 100): List<TaskExecution> {
        val rows = jdbc.query(
            """
            SELECT t.task_id, t.lock_version, tt.task_type_code, t.subject_id, t.aggregate_type, t.aggregate_id,
                   t.context_manifest::text AS context_manifest, t.trace_id,
                   wr.release_id, wr.agent_deployment_key, wr.agent_assistant_id, wr.agent_artifact_sha256,
                   wr.output_schema_version, wr.output_schema::text, wr.timeout_seconds, wr.max_attempts,
                   a.attempt_id, a.attempt_no, a.agent_run_id, a.agent_submission_state,
                   a.lease_owner, a.lease_version
              FROM healthmind.ai_tasks t
              JOIN healthmind.ai_task_types tt ON tt.task_type_id=t.task_type_id
              JOIN healthmind.workflow_releases wr ON wr.release_id=t.workflow_release_id
              JOIN healthmind.ai_task_attempts a ON a.task_id=t.task_id
             WHERE t.status='running' AND a.status='running' AND a.agent_managed
               AND a.started_at + (a.timeout_ms * INTERVAL '1 millisecond') < NOW()
               AND (a.lease_expires_at IS NULL OR a.lease_expires_at<=NOW())
               AND a.attempt_no=(SELECT MAX(latest.attempt_no) FROM healthmind.ai_task_attempts latest WHERE latest.task_id=t.task_id)
             ORDER BY a.started_at
             FOR UPDATE OF a SKIP LOCKED
             LIMIT :limit
            """.trimIndent(),
            mapOf("limit" to limit),
        ) { rs, _ -> rowToExecution(rs).copy(
            attemptId = rs.getObject("attempt_id", UUID::class.java),
            agentRunId = rs.getObject("agent_run_id", UUID::class.java),
            agentSubmissionState = AgentSubmissionState.valueOf(rs.getString("agent_submission_state").uppercase()),
            leaseOwner = rs.getString("lease_owner") ?: "",
            leaseVersion = rs.getLong("lease_version"),
        ) }
        val leaseUntil = Timestamp.from(Instant.now().plus(
            properties.agent.readTimeout.plus(properties.agent.connectTimeout).plus(Duration.ofSeconds(5)),
        ))
        return rows.map { command ->
            val updated = jdbc.update(
                """UPDATE healthmind.ai_task_attempts
                      SET lease_owner=:leaseOwner, lease_expires_at=:leaseExpiresAt, lease_version=lease_version+1
                    WHERE attempt_id=:attemptId AND status='running' AND lease_version=:leaseVersion""",
                mapOf(
                    "attemptId" to command.attemptId,
                    "leaseOwner" to workerId,
                    "leaseVersion" to command.leaseVersion,
                    "leaseExpiresAt" to leaseUntil,
                ),
            )
            check(updated == 1) { "Timed out Agent attempt lease was lost" }
            command.copy(leaseOwner = workerId, leaseVersion = command.leaseVersion + 1)
        }
    }

    @Transactional
    fun complete(command: TaskExecution, result: AgentRunResult, resultNode: JsonNode, outboxEvent: TaskOutboxMessage) {
        check(command.agentRunId == result.runId) { "Agent result run does not match the leased run" }
        val digest = canonicalJson.sha256(resultNode)
        val resultId = UUID.randomUUID()
        val confidence = resultNode.path("overall_confidence").takeUnless { it.isMissingNode || it.isNull }?.decimalValue()
        val attemptCompleted = jdbc.update(
            """
            UPDATE healthmind.ai_task_attempts SET status='succeeded', agent_run_id=:runId,
                   provider_name=:provider, model_name=:model, model_version=:modelVersion,
                   finished_at=NOW(), duration_ms=GREATEST(0, EXTRACT(EPOCH FROM (NOW()-started_at))*1000)::bigint,
                   input_tokens=:inputTokens, output_tokens=:outputTokens,
                   lease_owner=NULL, lease_expires_at=NULL, lease_version=lease_version+1
             WHERE attempt_id=:attemptId AND status='running' AND agent_run_id=:expectedRunId
               AND lease_owner=:leaseOwner AND lease_version=:leaseVersion
            """.trimIndent(),
            mapOf(
                "attemptId" to command.attemptId,
                "runId" to result.runId,
                "expectedRunId" to command.agentRunId,
                "provider" to result.providerName,
                "model" to result.modelName,
                "modelVersion" to result.modelVersion,
                "inputTokens" to result.inputTokens,
                "outputTokens" to result.outputTokens,
                "leaseOwner" to command.leaseOwner,
                "leaseVersion" to command.leaseVersion,
            ),
        )
        check(attemptCompleted == 1) { "Attempt completion lost its running state" }
        jdbc.update(
            """
            INSERT INTO healthmind.ai_task_results
                (result_id, task_id, attempt_id, workflow_release_id, agent_run_id, output_schema_version,
                 result_payload, result_sha256, confidence, produced_at, expires_at)
            VALUES (:resultId, :taskId, :attemptId, :releaseId, :runId, :schemaVersion,
                    CAST(:payload AS jsonb), :digest, :confidence, NOW(), :expiresAt)
            """.trimIndent(),
            mapOf(
                "resultId" to resultId,
                "taskId" to command.taskId,
                "attemptId" to command.attemptId,
                "releaseId" to command.releaseId,
                "runId" to result.runId,
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
        insertOutbox(command, outboxEvent)
    }

    @Transactional
    fun fail(
        command: TaskExecution,
        failure: Throwable,
        category: FailureCategory,
        code: String,
        outboxEvent: TaskOutboxMessage,
    ) {
        val sanitized = failure.message?.take(500) ?: code
        val attemptFailed = jdbc.update(
            """
            UPDATE healthmind.ai_task_attempts
               SET status=:status, finished_at=NOW(), failure_category=:category, failure_code=:code,
                   failure_message=:message,
                   duration_ms=GREATEST(0, EXTRACT(EPOCH FROM (NOW()-started_at))*1000)::bigint,
                   lease_owner=NULL, lease_expires_at=NULL, lease_version=lease_version+1
             WHERE attempt_id=:attemptId AND status='running'
               AND lease_owner=:leaseOwner AND lease_version=:leaseVersion
            """.trimIndent(),
            mapOf(
                "attemptId" to command.attemptId,
                "status" to if (category == FailureCategory.TIMEOUT) "timed_out" else "failed",
                "category" to category.wireValue,
                "code" to code,
                "message" to sanitized,
                "leaseOwner" to command.leaseOwner,
                "leaseVersion" to command.leaseVersion,
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
        insertOutbox(command, outboxEvent)
    }

    private fun insertOutbox(command: TaskExecution, event: TaskOutboxMessage) {
        val json = canonicalJson.stringify(event.payload)
        jdbc.update(
            """
            INSERT INTO healthmind.integration_outbox
                (event_id, task_id, event_type, schema_version, aggregate_type, aggregate_id,
                 destination_key, partition_key, payload, payload_sha256, trace_id, retention_until)
            VALUES (:eventId, :taskId, :eventType, :schemaVersion, :aggregateType, :aggregateId,
                    :destination, :partitionKey, CAST(:payload AS jsonb), :digest, :traceId, :retentionUntil)
            """.trimIndent(),
            mapOf(
                "eventId" to event.eventId,
                "taskId" to command.taskId,
                "eventType" to event.eventType,
                "schemaVersion" to event.schemaVersion,
                "aggregateType" to command.aggregateType,
                "aggregateId" to command.aggregateId,
                "destination" to event.destinationKey,
                "partitionKey" to event.partitionKey,
                "payload" to json,
                "digest" to canonicalJson.sha256(event.payload),
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
        taskTypeCode = rs.getString("task_type_code"),
        subjectId = rs.getObject("subject_id", UUID::class.java),
        aggregateType = rs.getString("aggregate_type"),
        aggregateId = rs.getString("aggregate_id"),
        contextManifest = rs.getString("context_manifest"),
        traceId = rs.getString("trace_id"),
        releaseId = rs.getObject("release_id", UUID::class.java),
        agentDeploymentKey = rs.getString("agent_deployment_key"),
        agentAssistantId = rs.getString("agent_assistant_id"),
        agentArtifactSha256 = rs.getString("agent_artifact_sha256"),
        outputSchemaVersion = rs.getString("output_schema_version"),
        outputSchema = rs.getString("output_schema"),
        timeoutSeconds = rs.getInt("timeout_seconds"),
        leaseOwner = rs.getString("lease_owner") ?: "",
        leaseVersion = rs.getLong("lease_version"),
    )

    private data class ProductionRelease(
        val taskTypeId: UUID,
        val releaseId: UUID,
        val inputSchemaVersion: String,
        val inputSchema: String,
    )
}
