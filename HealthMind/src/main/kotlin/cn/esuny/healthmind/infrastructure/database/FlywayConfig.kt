package cn.esuny.healthmind.infrastructure.database

import org.flywaydb.core.Flyway
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import javax.sql.DataSource

@Configuration
class FlywayConfig {
    @Bean(initMethod = "migrate")
    fun healthMindFlyway(dataSource: DataSource): Flyway = Flyway.configure()
        .dataSource(dataSource)
        .schemas("healthmind")
        .defaultSchema("healthmind")
        .createSchemas(true)
        .locations("classpath:db/migration")
        .load()
}
