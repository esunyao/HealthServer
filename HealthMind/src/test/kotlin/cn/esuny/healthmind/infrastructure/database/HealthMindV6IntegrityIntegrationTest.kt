package cn.esuny.healthmind.infrastructure.database

import cn.esuny.healthmind.application.service.MealTaskAdapter
import cn.esuny.healthmind.domain.task.AgentRunResult
import cn.esuny.healthmind.domain.task.TaskExecution
import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import cn.esuny.healthmind.infrastructure.config.FlywayConfig
import cn.esuny.healthmind.infrastructure.json.CanonicalJson
import cn.esuny.healthmind.infrastructure.json.JsonSchemaService
import cn.esuny.healthmind.infrastructure.messaging.HealthMindOutboxPublisher
import io.mockk.mockk
import org.flywaydb.core.Flyway
import org.flywaydb.core.api.FlywayException
import org.flywaydb.core.api.MigrationVersion
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.BeforeAll
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestInstance
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import org.springframework.jdbc.datasource.DataSourceTransactionManager
import org.springframework.jdbc.datasource.DriverManagerDataSource
import org.springframework.kafka.core.KafkaTemplate
import org.springframework.transaction.support.TransactionTemplate
import tools.jackson.databind.ObjectMapper
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class HealthMindV6IntegrityIntegrationTest {
    private lateinit var dataSource: DriverManagerDataSource
    private lateinit var jdbc: JdbcTemplate
    private val mapper = ObjectMapper()
    private val canonicalJson = CanonicalJson(mapper)

    @BeforeAll
    fun startPostgres() = TestPostgres.start()

    @AfterAll
    fun stopPostgres() = TestPostgres.stop()

    @BeforeEach
    fun resetToV5() {
        dataSource = TestPostgres.dataSource()
        dataSource.connection.use { connection ->
            connection.createStatement().use { it.execute("DROP SCHEMA IF EXISTS healthmind CASCADE") }
        }
        flyway("5").migrate()
        jdbc = JdbcTemplate(dataSource)
    }

    @Test
    fun `V6 preserves active task rows and adds release lease and attempt constraints`() {
        val releaseId = insertRelease()
        val taskId = insertTask(releaseId, status = "running")
        val attemptId = insertV5Attempt(taskId, attemptNo = 1, status = "running", submissionState = "new")
        insertInboxEvent()

        FlywayConfig().flyway(dataSource).migrate()

        assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM healthmind.ai_tasks WHERE task_id=?", Int::class.java, taskId))
        assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM healthmind.integration_inbox", Int::class.java))
        assertEquals(releaseId, jdbc.queryForObject(
            "SELECT workflow_release_id FROM healthmind.ai_task_attempts WHERE attempt_id=?", UUID::class.java, attemptId,
        ))
        assertEquals("v5-migration", jdbc.queryForObject(
            "SELECT lease_owner FROM healthmind.ai_task_attempts WHERE attempt_id=?", String::class.java, attemptId,
        ))
        assertEquals("uncertain", jdbc.queryForObject(
            "SELECT agent_submission_state FROM healthmind.ai_task_attempts WHERE attempt_id=?", String::class.java, attemptId,
        ))
        assertTrue(jdbc.queryForObject(
            "SELECT lease_expires_at<=NOW() FROM healthmind.ai_task_attempts WHERE attempt_id=?", Boolean::class.java, attemptId,
        ) == true)

        assertFailsWith<Exception> { insertV6Attempt(taskId, releaseId, attemptNo = 2, status = "pending") }

        val otherTypeId = insertTaskType("test.other")
        val otherReleaseId = insertRelease(otherTypeId)
        assertFailsWith<Exception> { insertMismatchedTask(otherTypeId, releaseId) }
        assertEquals(0, jdbc.queryForObject(
            "SELECT COUNT(*) FROM healthmind.ai_tasks WHERE workflow_release_id=? AND task_type_id=?",
            Int::class.java,
            releaseId,
            otherTypeId,
        ))
        assertTrue(jdbc.queryForObject(
            "SELECT COUNT(*) FROM healthmind.workflow_releases WHERE release_id=?", Int::class.java, otherReleaseId,
        ) == 1)
    }

    @Test
    fun `V6 rejects conflicting active attempts without clearing V5 data`() {
        val releaseId = insertRelease()
        val taskId = insertTask(releaseId, status = "running")
        insertV5Attempt(taskId, attemptNo = 1, status = "running")
        insertV5Attempt(taskId, attemptNo = 2, status = "pending")

        val error = assertFailsWith<FlywayException> { FlywayConfig().flyway(dataSource).migrate() }

        assertTrue(error.message.orEmpty().contains("multiple active attempts"))
        assertEquals(2, jdbc.queryForObject(
            "SELECT COUNT(*) FROM healthmind.ai_task_attempts WHERE task_id=?", Int::class.java, taskId,
        ))
        assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM healthmind.ai_tasks WHERE task_id=?", Int::class.java, taskId))
        assertEquals(5, jdbc.queryForObject(
            "SELECT COUNT(*) FROM healthmind.flyway_schema_history WHERE success AND version IS NOT NULL", Int::class.java,
        ))
        assertFalse(jdbc.queryForObject(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='healthmind' AND table_name='ai_task_attempts' AND column_name='lease_owner')",
            Boolean::class.java,
        ) == true)
    }

    @Test
    fun `stable tool call replay does not consume another call and changed request is rejected`() {
        val releaseId = insertRelease()
        bindTool(releaseId, "nutrimemo.capture_context.get")
        FlywayConfig().flyway(dataSource).migrate()
        promoteRelease(releaseId)
        val taskId = insertTask(releaseId, status = "running")
        val attemptId = insertV6Attempt(taskId, releaseId, attemptNo = 1, status = "running")
        val toolId = jdbc.queryForObject(
            "SELECT tool_id FROM healthmind.ai_tool_definitions WHERE tool_code='nutrimemo.capture_context.get'",
            UUID::class.java,
        )!!
        val scope = jdbc.queryForObject(
            "SELECT auth_scope FROM healthmind.ai_tool_definitions WHERE tool_id=?", String::class.java, toolId,
        )!!
        val repository = ToolInvocationRepository(NamedParameterJdbcTemplate(dataSource), canonicalJson)
        val toolCallId = UUID.randomUUID().toString()
        val request = canonicalJson.parse("""{"attempt_id":"$attemptId","task_id":"$taskId"}""")

        val first = repository.authorizeAndStart(
            "nutrimemo.capture_context.get", taskId, attemptId, toolCallId, request, null, setOf(scope),
        )
        val inProgress = assertFailsWith<ToolAccessException> {
            repository.authorizeAndStart(
                "nutrimemo.capture_context.get", taskId, attemptId, toolCallId, request, null, setOf(scope),
            )
        }
        assertEquals("TOOL_CALL_IN_PROGRESS", inProgress.code)
        assertEquals(0, jdbc.queryForObject(
            "SELECT replay_count FROM healthmind.ai_tool_invocations WHERE invocation_id=?", Int::class.java, first.invocationId,
        ))
        repository.succeed(first, "b".repeat(64))
        val replay = repository.authorizeAndStart(
            "nutrimemo.capture_context.get", taskId, attemptId, toolCallId, request, null, setOf(scope),
        )

        assertEquals(first.invocationId, replay.invocationId)
        assertTrue(replay.isReplay)
        assertEquals(1, jdbc.queryForObject(
            "SELECT replay_count FROM healthmind.ai_tool_invocations WHERE invocation_id=?", Int::class.java, first.invocationId,
        ))
        assertEquals(1, jdbc.queryForObject(
            "SELECT COUNT(*) FROM healthmind.ai_tool_invocations WHERE attempt_id=? AND tool_id=?",
            Int::class.java,
            attemptId,
            toolId,
        ))

        val changedRequest = canonicalJson.parse("""{"attempt_id":"$attemptId","task_id":"$taskId","other":"changed"}""")
        val conflict = assertFailsWith<ToolAccessException> {
            repository.authorizeAndStart(
                "nutrimemo.capture_context.get", taskId, attemptId, toolCallId, changedRequest, null, setOf(scope),
            )
        }
        assertEquals("TOOL_IDEMPOTENCY_CONFLICT", conflict.code)
    }

    @Test
    fun `old attempt lease and stale outbox publisher cannot overwrite newer state`() {
        FlywayConfig().flyway(dataSource).migrate()
        val releaseId = insertRelease()
        val taskId = insertTask(releaseId, status = "running")
        val runId = UUID.randomUUID()
        val attemptId = insertV6Attempt(taskId, releaseId, attemptNo = 1, status = "running", runId = runId)
        val command = taskExecution(taskId, attemptId, releaseId, runId)
        val stale = command.copy(leaseOwner = "old-worker", leaseVersion = 1)
        val output = canonicalJson.parse("""{"overall_confidence":0.9,"items":[]}""")
        val properties = HealthMindProperties()
        val mealAdapter = MealTaskAdapter(mapper, canonicalJson, properties)
        val taskRepository = TaskCommandRepository(
            NamedParameterJdbcTemplate(dataSource), canonicalJson, JsonSchemaService(canonicalJson), properties,
        )

        assertFailsWith<IllegalStateException> {
            taskRepository.complete(stale, AgentRunResult(runId, canonicalJson.stringify(output)), output, mealAdapter.completedEvent(stale, output))
        }
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM healthmind.ai_task_results WHERE task_id=?", Int::class.java, taskId))
        assertEquals("running", jdbc.queryForObject(
            "SELECT status FROM healthmind.ai_task_attempts WHERE attempt_id=?", String::class.java, attemptId,
        ))

        val eventId = UUID.randomUUID()
        insertOutbox(taskId, eventId)
        val transactions = TransactionTemplate(DataSourceTransactionManager(dataSource))
        val publisher = HealthMindOutboxPublisher(
            NamedParameterJdbcTemplate(dataSource),
            mockk<KafkaTemplate<String, String>>(relaxed = true),
            transactions,
            properties,
        )
        val firstClaim = requireNotNull(transactions.execute { publisher.claim() })
        jdbc.update(
            "UPDATE healthmind.integration_outbox SET status='failed', failure_code='PUBLISHER_INTERRUPTED', failure_message='Recovered publisher', next_attempt_at=NOW(), claim_version=claim_version+1 WHERE event_id=?",
            eventId,
        )
        transactions.executeWithoutResult { publisher.markPublished(eventId, firstClaim.claimVersion) }
        assertEquals("failed", jdbc.queryForObject(
            "SELECT status FROM healthmind.integration_outbox WHERE event_id=?", String::class.java, eventId,
        ))

        val secondClaim = requireNotNull(transactions.execute { publisher.claim() })
        assertTrue(secondClaim.claimVersion > firstClaim.claimVersion)
        transactions.executeWithoutResult {
            publisher.markFailed(eventId, firstClaim.claimVersion, "STALE", "stale publisher")
        }
        assertEquals("publishing", jdbc.queryForObject(
            "SELECT status FROM healthmind.integration_outbox WHERE event_id=?", String::class.java, eventId,
        ))
        transactions.executeWithoutResult { publisher.markPublished(eventId, secondClaim.claimVersion) }
        assertEquals("published", jdbc.queryForObject(
            "SELECT status FROM healthmind.integration_outbox WHERE event_id=?", String::class.java, eventId,
        ))
        assertFailsWith<Exception> { jdbc.update("DELETE FROM healthmind.integration_outbox WHERE event_id=?", eventId) }
    }

    private fun flyway(target: String): Flyway = Flyway.configure()
        .dataSource(dataSource)
        .schemas("healthmind")
        .defaultSchema("healthmind")
        .createSchemas(true)
        .placeholderReplacement(false)
        .locations("classpath:db/migration")
        .target(MigrationVersion.fromVersion(target))
        .load()

    private fun insertRelease(taskTypeId: UUID = mealTaskTypeId()): UUID {
        val releaseId = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO healthmind.workflow_releases
                   (release_id, task_type_id, release_version, status, agent_deployment_key, agent_assistant_id,
                    agent_artifact_sha256, input_schema_version, input_schema, input_schema_sha256,
                    output_schema_version, output_schema, output_schema_sha256, timeout_seconds, max_attempts)
                 VALUES (?, ?, 'test-v1', 'candidate', 'test-deployment', 'test-assistant', ?, '1.0', '{}'::jsonb, ?,
                         '1.0', '{}'::jsonb, ?, 120, 3)""",
            releaseId,
            taskTypeId,
            "a".repeat(64),
            "b".repeat(64),
            "c".repeat(64),
        )
        return releaseId
    }

    private fun insertTask(releaseId: UUID, status: String): UUID {
        val taskId = UUID.randomUUID()
        val taskTypeId = jdbc.queryForObject(
            "SELECT task_type_id FROM healthmind.workflow_releases WHERE release_id=?", UUID::class.java, releaseId,
        )!!
        jdbc.update(
            """INSERT INTO healthmind.ai_tasks
                   (task_id, task_type_id, workflow_release_id, requester_service, aggregate_type, aggregate_id,
                    idempotency_key, status, started_at, trace_id, input_schema_version, input_digest, retention_until)
                 VALUES (?, ?, ?, 'test', 'meal', '42', ?, ?, CASE WHEN ?='running' THEN NOW() ELSE NULL END,
                         'test-trace', '1.0', ?, NOW()+INTERVAL '2 days')""",
            taskId,
            taskTypeId,
            releaseId,
            taskId.toString(),
            status,
            status,
            "e".repeat(64),
        )
        return taskId
    }

    private fun insertV5Attempt(taskId: UUID, attemptNo: Int, status: String, submissionState: String = "uncertain"): UUID {
        val attemptId = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO healthmind.ai_task_attempts
                   (attempt_id, task_id, attempt_no, status, started_at, timeout_ms, agent_managed, agent_submission_state)
                 VALUES (?, ?, ?, ?, NOW(), 120000, TRUE, ?)""",
            attemptId,
            taskId,
            attemptNo,
            status,
            submissionState,
        )
        return attemptId
    }

    private fun insertV6Attempt(taskId: UUID, releaseId: UUID, attemptNo: Int, status: String, runId: UUID? = null): UUID {
        val attemptId = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO healthmind.ai_task_attempts
                   (attempt_id, task_id, workflow_release_id, attempt_no, status, started_at, timeout_ms,
                    agent_managed, agent_submission_state, agent_run_id, lease_owner, lease_expires_at, lease_version)
                 VALUES (?, ?, ?, ?, ?, NOW(), 120000, TRUE, 'attached', ?, 'new-worker', NOW()+INTERVAL '30 seconds', 2)""",
            attemptId,
            taskId,
            releaseId,
            attemptNo,
            status,
            runId,
        )
        return attemptId
    }

    private fun insertInboxEvent() {
        jdbc.update(
            """INSERT INTO healthmind.integration_inbox
                   (event_id, event_type, schema_version, producer, aggregate_type, aggregate_id, trace_id,
                    payload_sha256, retention_until)
                 VALUES (?, 'test.event', '1.0', 'test', 'meal', '42', 'trace', ?, NOW()+INTERVAL '2 days')""",
            UUID.randomUUID(),
            "f".repeat(64),
        )
    }

    private fun insertTaskType(code: String): UUID {
        val id = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO healthmind.ai_task_types (task_type_id, task_type_code, domain_code, display_name)
                 VALUES (?, ?, 'test', 'Test task')""",
            id,
            code,
        )
        return id
    }

    private fun insertMismatchedTask(taskTypeId: UUID, releaseId: UUID) {
        jdbc.update(
            """INSERT INTO healthmind.ai_tasks
                   (task_id, task_type_id, workflow_release_id, requester_service, aggregate_type, aggregate_id,
                    idempotency_key, trace_id, input_schema_version, input_digest, retention_until)
                 VALUES (?, ?, ?, 'test', 'meal', '99', ?, 'trace', '1.0', ?, NOW()+INTERVAL '1 day')""",
            UUID.randomUUID(),
            taskTypeId,
            releaseId,
            UUID.randomUUID().toString(),
            "1".repeat(64),
        )
    }

    private fun bindTool(releaseId: UUID, toolCode: String) {
        jdbc.update(
            """INSERT INTO healthmind.workflow_release_tools (release_id, tool_id, allowed_scope, max_calls)
                 SELECT ?, tool_id, auth_scope, 1 FROM healthmind.ai_tool_definitions WHERE tool_code=?""",
            releaseId,
            toolCode,
        )
    }

    private fun promoteRelease(releaseId: UUID) {
        jdbc.update(
            "UPDATE healthmind.workflow_releases SET status='production', promoted_at=NOW() WHERE release_id=?",
            releaseId,
        )
    }

    private fun insertOutbox(taskId: UUID, eventId: UUID) {
        jdbc.update(
            """INSERT INTO healthmind.integration_outbox
                   (event_id, task_id, event_type, schema_version, aggregate_type, aggregate_id, destination_key,
                    partition_key, payload, payload_sha256, trace_id, retention_until)
                 VALUES (?, ?, 'test.event', '1.0', 'meal', '42', 'test-topic', '42', '{}'::jsonb, ?, 'trace', NOW()+INTERVAL '1 day')""",
            eventId,
            taskId,
            "2".repeat(64),
        )
    }

    private fun taskExecution(taskId: UUID, attemptId: UUID, releaseId: UUID, runId: UUID) = TaskExecution(
        taskId = taskId,
        attemptId = attemptId,
        attemptNo = 1,
        maxAttempts = 3,
        lockVersion = 1,
        taskTypeCode = MealTaskAdapter.MEAL_ANALYSIS_TASK_TYPE,
        subjectId = UUID.randomUUID(),
        aggregateType = "meal",
        aggregateId = "42",
        contextManifest = """{"capture_session_id":"${UUID.randomUUID()}","meal_id":42}""",
        traceId = "trace",
        releaseId = releaseId,
        agentDeploymentKey = "test-deployment",
        agentAssistantId = "test-assistant",
        agentArtifactSha256 = "a".repeat(64),
        agentRunId = runId,
        outputSchemaVersion = "1.0",
        outputSchema = "{}",
        timeoutSeconds = 120,
        leaseOwner = "new-worker",
        leaseVersion = 2,
    )

    private fun mealTaskTypeId(): UUID = jdbc.queryForObject(
        "SELECT task_type_id FROM healthmind.ai_task_types WHERE task_type_code='nutrition.meal_analysis'",
        UUID::class.java,
    )!!

}
