package cn.esuny.healthmind.infrastructure.database

import cn.esuny.healthmind.infrastructure.config.FlywayConfig
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.BeforeAll
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestInstance
import org.springframework.jdbc.core.JdbcTemplate
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import java.util.UUID

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class AgentReleaseRegistrationIntegrationTest {
    private lateinit var jdbc: JdbcTemplate

    @BeforeAll
    fun startPostgres() = TestPostgres.start()

    @AfterAll
    fun stopPostgres() = TestPostgres.stop()

    @BeforeEach
    fun migrateFreshSchemaThroughV6() {
        val dataSource = TestPostgres.dataSource()
        dataSource.connection.use { connection ->
            connection.createStatement().use { it.execute("DROP SCHEMA IF EXISTS healthmind CASCADE") }
        }
        assertTrue(FlywayConfig().flyway(dataSource).migrate().success)
        jdbc = JdbcTemplate(dataSource)
    }

    @Test
    fun `psql registration snapshots tool schemas and promoted release remains valid`() {
        val releaseId = UUID.randomUUID()
        val actorId = UUID.randomUUID()
        val variables = linkedMapOf(
            "release_id" to releaseId.toString(),
            "release_version" to "registration-test-v1",
            "deployment_key" to "registration-test-deployment",
            "assistant_id" to "registration-test-assistant",
            "artifact_sha256" to "a".repeat(64),
            "input_schema_version" to "1.0",
            "input_schema" to """{"type":"object","additionalProperties":false}""",
            "input_schema_sha256" to "b".repeat(64),
            "output_schema_version" to "1.0",
            "output_schema" to """{"type":"object","additionalProperties":false}""",
            "output_schema_sha256" to "c".repeat(64),
            "timeout_seconds" to "120",
            "max_attempts" to "3",
            "actor_id" to actorId.toString(),
            "reason" to "PostgreSQL registration regression",
            "trace_id" to "registration-regression",
        )

        jdbc.update(
            "UPDATE healthmind.ai_tool_definitions SET active=FALSE WHERE tool_code='orion.nutrition_context.get'",
        )
        assertFailsWith<IllegalStateException> {
            TestPostgres.executePsql("/db/manual/register_agent_release.sql", variables)
        }
        assertEquals(0, jdbc.queryForObject(
            "SELECT COUNT(*) FROM healthmind.workflow_releases WHERE release_id=?", Int::class.java, releaseId,
        ))
        assertEquals(0, jdbc.queryForObject(
            "SELECT COUNT(*) FROM healthmind.workflow_release_tools WHERE release_id=?", Int::class.java, releaseId,
        ))
        assertEquals(0, jdbc.queryForObject(
            "SELECT COUNT(*) FROM healthmind.workflow_release_audits WHERE release_id=?", Int::class.java, releaseId,
        ))

        jdbc.update(
            "UPDATE healthmind.ai_tool_definitions SET active=TRUE WHERE tool_code='orion.nutrition_context.get'",
        )
        TestPostgres.executePsql("/db/manual/register_agent_release.sql", variables)

        assertEquals("candidate", jdbc.queryForObject(
            "SELECT status FROM healthmind.workflow_releases WHERE release_id=?", String::class.java, releaseId,
        ))
        assertEquals(2, jdbc.queryForObject(
            "SELECT COUNT(*) FROM healthmind.workflow_release_tools WHERE release_id=?", Int::class.java, releaseId,
        ))
        assertEquals(0, jdbc.queryForObject(
            """SELECT COUNT(*)
                 FROM healthmind.workflow_release_tools rt
                 JOIN healthmind.ai_tool_definitions d USING (tool_id)
                WHERE rt.release_id=? AND (
                    rt.request_schema_version IS DISTINCT FROM d.request_schema_version OR
                    rt.request_schema IS DISTINCT FROM d.request_schema OR
                    rt.request_schema_sha256 IS DISTINCT FROM d.request_schema_sha256 OR
                    rt.response_schema_version IS DISTINCT FROM d.response_schema_version OR
                    rt.response_schema IS DISTINCT FROM d.response_schema OR
                    rt.response_schema_sha256 IS DISTINCT FROM d.response_schema_sha256
                )""",
            Int::class.java,
            releaseId,
        ))

        TestPostgres.executePsql(
            "/db/manual/promote_workflow_release.sql",
            mapOf(
                "release_id" to releaseId.toString(),
                "actor_id" to actorId.toString(),
                "reason" to "PostgreSQL registration regression promotion",
                "trace_id" to "registration-regression-promotion",
            ),
        )
        assertEquals("production", jdbc.queryForObject(
            "SELECT status FROM healthmind.workflow_releases WHERE release_id=?", String::class.java, releaseId,
        ))
    }
}
