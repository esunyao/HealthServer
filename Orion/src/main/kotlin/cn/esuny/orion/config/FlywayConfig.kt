package cn.esuny.orion.config

import org.flywaydb.core.Flyway
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import javax.sql.DataSource

/**
 * Flyway 迁移配置
 *
 * 为什么不在这里设置 .schemas()：
 * Flyway 会对传入的 schema 名再次加引号，导致 """User"""（三重引号）这个错误标识符，
 * 最终触发 CREATE SCHEMA """User""" 并因权限不足失败。
 *
 * 正确做法：
 * 不调用 .schemas()，Flyway 直接继承 HikariCP 连接池的连接。
 * JDBC URL 中 currentSchema=User 已由 PostgreSQL JDBC 驱动在连接层设置了
 * search_path = "User"，Flyway 会在该 schema 下创建 flyway_schema_history 并执行迁移。
 */
@Configuration
class FlywayConfig {

    // 指定 Spring 容器在创建完 Flyway Bean 后，自动调用其 migrate() 方法，从而触发数据库迁移脚本的执行。
    @Bean(initMethod = "migrate")
    fun flyway(dataSource: DataSource): Flyway {
        return Flyway.configure()
            .dataSource(dataSource)
            // 不设置 schemas()：复用 JDBC URL currentSchema=User 的 search_path
            // Flyway 会在 "User" schema 下自动创建 flyway_schema_history
            .locations("classpath:db/migration")
            // schema 中已有 users/user_profiles/refresh_tokens（手动建的，非 Flyway 管理）
            // baselineOnMigrate: 首次运行时在 version=0 处写入 baseline 记录
            // baselineVersion("0"): baseline 版本为 0，V1 > 0 所以会被正常执行
            .baselineOnMigrate(true)
            .baselineVersion("0")
            .load()
    }
}

