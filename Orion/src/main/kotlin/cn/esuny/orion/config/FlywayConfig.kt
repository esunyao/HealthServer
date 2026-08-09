package cn.esuny.orion.config

import org.flywaydb.core.Flyway
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import javax.sql.DataSource

/** Authentik 迁移后的 Orion Schema。 */
@Configuration
class FlywayConfig {

    @Bean(initMethod = "migrate")
    fun flyway(dataSource: DataSource): Flyway {
        return Flyway.configure()
            .dataSource(dataSource)
            .schemas("orion")
            .defaultSchema("orion")
            .createSchemas(true)
            .locations("classpath:db/migration")
            .load()
    }
}
