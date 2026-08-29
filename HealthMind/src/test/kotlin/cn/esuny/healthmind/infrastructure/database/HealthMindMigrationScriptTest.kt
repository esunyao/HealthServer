package cn.esuny.healthmind.infrastructure.database

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class HealthMindMigrationScriptTest {
    private val migration = requireNotNull(javaClass.getResource("/db/migration/V1__create_healthmind_schema.sql")).readText()

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
}
