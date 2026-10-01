package cn.esuny.healthmind.infrastructure.database

import org.springframework.jdbc.datasource.DriverManagerDataSource
import org.testcontainers.containers.PostgreSQLContainer
import org.testcontainers.utility.MountableFile
import java.net.URI
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption

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

    @Synchronized
    fun executePsql(resourcePath: String, variables: Map<String, String>) {
        val script = Files.createTempFile("healthmind-psql-", ".sql")
        try {
            val resource = requireNotNull(TestPostgres::class.java.getResourceAsStream(resourcePath)) {
                "Missing SQL resource $resourcePath"
            }
            resource.use { Files.copy(it, script, StandardCopyOption.REPLACE_EXISTING) }
            val output = if (externalUrl == null) {
                executeContainerPsql(script, variables)
            } else {
                executeHostPsql(script, variables)
            }
            if (output.first != 0) {
                throw IllegalStateException("psql failed (${output.first}): ${output.second}")
            }
        } finally {
            Files.deleteIfExists(script)
        }
    }

    private fun executeContainerPsql(script: Path, variables: Map<String, String>): Pair<Int, String> {
        val containerPath = "/tmp/${script.fileName}"
        container.copyFileToContainer(MountableFile.forHostPath(script), containerPath)
        val command = mutableListOf(
            "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", container.username,
            "-d", container.databaseName, "-f", containerPath,
        )
        variables.forEach { (name, value) -> command.addAll(listOf("-v", "$name=$value")) }
        val result = container.execInContainer(*command.toTypedArray())
        return result.exitCode to (result.stdout + result.stderr)
    }

    private fun executeHostPsql(script: Path, variables: Map<String, String>): Pair<Int, String> {
        val uri = URI(requireNotNull(externalUrl).removePrefix("jdbc:"))
        val command = mutableListOf("psql", "-X", "-v", "ON_ERROR_STOP=1", "-h", uri.host)
        if (uri.port >= 0) command.addAll(listOf("-p", uri.port.toString()))
        command.addAll(listOf(
            "-d", uri.path.removePrefix("/"),
            "-U", System.getenv("HEALTHMIND_TEST_JDBC_USER")?.takeIf(String::isNotBlank) ?: "postgres",
            "-f", script.toAbsolutePath().toString(),
        ))
        variables.forEach { (name, value) -> command.addAll(listOf("-v", "$name=$value")) }
        val process = ProcessBuilder(command).redirectErrorStream(true)
        System.getenv("HEALTHMIND_TEST_JDBC_PASSWORD")?.let { process.environment()["PGPASSWORD"] = it }
        val child = process.start()
        val output = child.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        return child.waitFor() to output
    }
}
