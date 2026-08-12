package cn.esuny.nutrimemo.config

import org.flywaydb.core.Flyway
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import javax.sql.DataSource

/** NutriMemo 独占 nutri Schema，迁移不触碰 Orion 的表。 */
@Configuration
class FlywayConfig {
    @Bean(initMethod = "migrate")
    fun flyway(dataSource: DataSource): Flyway = Flyway.configure()
        .dataSource(dataSource)
        .schemas("nutri")
        .defaultSchema("nutri")
        .createSchemas(true)
        .locations("classpath:db/migration")
        .load()
}
