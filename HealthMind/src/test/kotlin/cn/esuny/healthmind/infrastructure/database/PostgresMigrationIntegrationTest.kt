package cn.esuny.healthmind.infrastructure.database

import cn.esuny.healthmind.infrastructure.config.FlywayConfig
import org.junit.jupiter.api.Test
import org.springframework.jdbc.datasource.DriverManagerDataSource
import org.testcontainers.containers.PostgreSQLContainer
import org.testcontainers.junit.jupiter.Container
import org.testcontainers.junit.jupiter.Testcontainers
import kotlin.test.assertEquals
import kotlin.test.assertTrue

@Testcontainers(disabledWithoutDocker = true)
class PostgresMigrationIntegrationTest {
    @Test
    fun `postgres 17 applies migration and creates twelve tables`() {
        val dataSource = DriverManagerDataSource(postgres.jdbcUrl, postgres.username, postgres.password)
        val flyway = FlywayConfig().flyway(dataSource)

        val migrationResult = flyway.migrate()

        assertTrue(migrationResult.success)
        assertEquals("healthmind", flyway.configuration.defaultSchema)

        postgres.createConnection("").use { connection ->
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
        }
    }

    companion object {
        @Container
        @JvmStatic
        val postgres = PostgreSQLContainer("postgres:17-alpine")
    }
}
