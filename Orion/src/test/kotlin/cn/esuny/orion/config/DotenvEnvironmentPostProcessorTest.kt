package cn.esuny.orion.config

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import org.springframework.boot.SpringApplication
import org.springframework.boot.WebApplicationType
import org.springframework.context.annotation.Configuration
import java.io.File
import java.nio.file.Path
import kotlin.test.assertEquals

/**
 * 验证 spring-dotenv（springboot4-dotenv:5.1.0）能通过 SPI 注册并读取 .env 文件。
 *
 * 使用纯 @Configuration（不启用自动配置），因此不会触发 Nacos / Redis / 数据源连接。
 * 用 spring.config.import 置空来跳过 application.yaml 里的 Nacos 远程配置导入，
 * 并让 springdotenv.directory 指向临时目录，保证测试与仓库内的真实 .env 无关。
 */
class DotenvEnvironmentPostProcessorTest {

    @Configuration
    class EmptyConfig

    @Test
    fun `dotenv 变量被注入到 Spring Environment`(@TempDir tempDir: Path) {
        // 构造临时 .env
        File(tempDir.toFile(), ".env").writeText(
            """
            TEST_DOTENV_VAR=hello-from-dotenv
            JWT_SECRET=dotenv-jwt-secret
            """.trimIndent()
        )

        val app = SpringApplication(EmptyConfig::class.java)
        app.setWebApplicationType(WebApplicationType.NONE)
        app.setDefaultProperties(
            mapOf(
                "spring.config.import" to "",
                "springdotenv.directory" to tempDir.toString()
            )
        )

        val context = app.run()
        try {
            assertEquals("hello-from-dotenv", context.environment.getProperty("TEST_DOTENV_VAR"))
            assertEquals("dotenv-jwt-secret", context.environment.getProperty("JWT_SECRET"))
        } finally {
            context.close()
        }
    }
}
