package cn.esuny.healthmind.infrastructure.database

import org.springframework.jdbc.datasource.DriverManagerDataSource
import org.testcontainers.containers.PostgreSQLContainer

/** Uses an isolated PostgreSQL 17 container by default; an explicit test-only JDBC URL can be supplied by CI. */
internal object TestPostgres {
    private val container = PostgreSQLContainer("postgres:17-alpine")
    private val externalUrl: String? = System.getenv("HEALTHMIND_TEST_JDBC_URL")?.takeIf(String::isNotBlank)

    @Synchronized
    fun start() {
        if (externalUrl == null && !container.isRunning) container.start()
    }

    @Synchronized
    fun stop() {
        if (externalUrl == null && container.isRunning) container.stop()
    }

    fun dataSource(): DriverManagerDataSource = DriverManagerDataSource(
        externalUrl ?: container.jdbcUrl,
        System.getenv("HEALTHMIND_TEST_JDBC_USER")?.takeIf(String::isNotBlank)
            ?: if (externalUrl == null) container.username else "postgres",
        System.getenv("HEALTHMIND_TEST_JDBC_PASSWORD") ?: if (externalUrl == null) container.password else "",
    )
}
