package cn.esuny.healthmind.infrastructure.database

import cn.esuny.healthmind.infrastructure.config.FlywayConfig
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.BeforeAll
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestInstance
import kotlin.test.assertEquals
import kotlin.test.assertTrue

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class PostgresMigrationIntegrationTest {
    @BeforeAll
    fun startPostgres() = TestPostgres.start()

    @AfterAll
    fun stopPostgres() = TestPostgres.stop()

    @Test
    fun `postgres 17 applies migration and creates twelve tables`() {
        val dataSource = TestPostgres.dataSource()
        val flyway = FlywayConfig().flyway(dataSource)

        val migrationResult = flyway.migrate()

        assertTrue(migrationResult.success)
        assertEquals("healthmind", flyway.configuration.defaultSchema)

        dataSource.connection.use { connection ->
            connection.prepareStatement(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='healthmind' AND table_type='BASE TABLE' AND table_name <> 'flyway_schema_history'",
            ).use { statement ->
                statement.executeQuery().use { result ->
                    result.next()
                    assertEquals(12, result.getInt(1))
                }
            }
            connection.prepareStatement(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='healthmind' AND table_name='flyway_schema_history'",
            ).use { statement ->
                statement.executeQuery().use { result ->
                    result.next()
                    assertEquals(1, result.getInt(1))
                }
            }
            connection.prepareStatement(
                "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='healthmind' AND column_name LIKE 'dify_%'",
            ).use { statement ->
                statement.executeQuery().use { result ->
                    result.next()
                    assertEquals(0, result.getInt(1))
                }
            }
            connection.prepareStatement(
                "SELECT COUNT(*) FROM healthmind.ai_tool_definitions",
            ).use { statement ->
                statement.executeQuery().use { result ->
                    result.next()
                    assertEquals(2, result.getInt(1))
                }
            }
            connection.prepareStatement(
                "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='healthmind' AND table_name='ai_task_attempts' AND column_name IN ('workflow_release_id','lease_owner','lease_expires_at','lease_version')",
            ).use { statement ->
                statement.executeQuery().use { result ->
                    result.next()
                    assertEquals(4, result.getInt(1))
                }
            }
            connection.prepareStatement(
                "SELECT COUNT(*) FROM pg_indexes WHERE schemaname='healthmind' AND indexname='uk_ai_task_attempts_active_task'",
            ).use { statement ->
                statement.executeQuery().use { result ->
                    result.next()
                    assertEquals(1, result.getInt(1))
                }
            }
        }
    }

}
