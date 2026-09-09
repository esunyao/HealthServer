package cn.esuny.healthmind.infrastructure.config

import org.flywaydb.core.Flyway
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import javax.sql.DataSource

/** HealthMind 数据库迁移配置。 */
@Configuration
class FlywayConfig {

    @Bean(initMethod = "migrate")
    fun flyway(dataSource: DataSource): Flyway {
        return Flyway.configure()
            .dataSource(dataSource)
            .schemas("healthmind")
            .defaultSchema("healthmind")
            .createSchemas(true)
            .placeholderReplacement(false)
            .locations("classpath:db/migration")
            .load()
    }
}
