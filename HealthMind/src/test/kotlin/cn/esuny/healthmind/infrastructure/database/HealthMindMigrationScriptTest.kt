package cn.esuny.healthmind.infrastructure.database

import cn.esuny.healthmind.infrastructure.config.FlywayConfig
import org.springframework.jdbc.datasource.DriverManagerDataSource
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class HealthMindMigrationScriptTest {
    private val migration = requireNotNull(javaClass.getResource("/db/migration/V1__create_healthmind_schema.sql")).readText()
    private val seeds = requireNotNull(javaClass.getResource("/db/migration/V2__seed_stable_definitions.sql")).readText()
    private val cutover = requireNotNull(javaClass.getResource("/db/migration/V4__replace_dify_with_agent_runs.sql")).readText()

    @Test
    fun `migration declares workbook twelve tables`() {
        val tables = Regex("(?m)^CREATE TABLE ([a-z_]+) ").findAll(migration).map { it.groupValues[1] }.toSet()
        assertEquals(
            setOf(
                "ai_task_types", "workflow_releases", "workflow_release_audits", "ai_tool_definitions",
                "workflow_release_tools", "ai_tasks", "ai_task_attempts", "ai_task_results",
                "ai_task_artifacts", "ai_tool_invocations", "integration_inbox", "integration_outbox",
            ),
            tables,
        )
    }

    @Test
    fun `migration includes concurrency and lifecycle constraints`() {
        assertTrue(migration.contains("uk_workflow_releases_production"))
        assertTrue(migration.contains("uk_ai_tasks_idempotency"))
        assertTrue(migration.contains("ck_ai_tasks_lifecycle"))
        assertTrue(migration.contains("idx_integration_outbox_delivery"))
    }

    @Test
    fun `stable tools seed explicit request and response contracts`() {
        assertTrue(seeds.contains("\"required\":[\"attempt_id\",\"task_id\"]"))
        assertTrue(seeds.contains("\"required\":[\"capture_session_id\",\"meal_id\",\"meal_type\""))
        assertTrue(seeds.contains("\"required\":[\"subject_id\",\"age_years\",\"gender\""))
        assertTrue(seeds.contains("'{}'::jsonb").not())
    }

    @Test
    fun `agent cutover keeps stable definitions and replaces provider fields`() {
        assertTrue(cutover.contains("TRUNCATE TABLE"))
        assertFalse(cutover.contains("healthmind.ai_task_types,"))
        assertFalse(cutover.contains("healthmind.ai_tool_definitions,"))
        assertTrue(cutover.contains("ADD COLUMN agent_deployment_key"))
        assertTrue(cutover.contains("ADD COLUMN agent_run_id UUID"))
        assertTrue(cutover.contains("ADD COLUMN agent_managed BOOLEAN NOT NULL DEFAULT FALSE"))
        assertTrue(cutover.contains("DROP COLUMN dify_workflow_run_id"))
        assertTrue(cutover.contains("trg_protect_agent_release_identity"))
        assertTrue(cutover.contains("trg_protect_promoted_agent_tools"))
    }

    @Test
    fun `flyway does not interpret json schema as placeholders`() {
        val dataSource = DriverManagerDataSource("jdbc:postgresql://localhost:1/unused", "unused", "unused")

        val flyway = FlywayConfig().flyway(dataSource)

        assertFalse(flyway.configuration.isPlaceholderReplacement)
    }
}
