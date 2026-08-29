package cn.esuny.healthmind.infrastructure.database

import org.flywaydb.core.Flyway
import org.junit.jupiter.api.Test
import org.testcontainers.containers.PostgreSQLContainer
import org.testcontainers.junit.jupiter.Container
import org.testcontainers.junit.jupiter.Testcontainers
import kotlin.test.assertEquals

@Testcontainers(disabledWithoutDocker = true)
class PostgresMigrationIntegrationTest {
    @Test
    fun `postgres 17 applies migration and creates twelve tables`() {
        Flyway.configure()
            .dataSource(postgres.jdbcUrl, postgres.username, postgres.password)
            .schemas("healthmind")
            .defaultSchema("healthmind")
            .createSchemas(true)
            .locations("classpath:db/migration")
            .load()
            .migrate()

        postgres.createConnection("").use { connection ->
            connection.prepareStatement(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='healthmind' AND table_type='BASE TABLE' AND table_name <> 'flyway_schema_history'",
            ).use { statement ->
                statement.executeQuery().use { result ->
                    result.next()
                    assertEquals(12, result.getInt(1))
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
