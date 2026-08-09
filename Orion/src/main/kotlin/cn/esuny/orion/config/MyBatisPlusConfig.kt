package cn.esuny.orion.config

import com.baomidou.mybatisplus.annotation.DbType
import com.baomidou.mybatisplus.autoconfigure.ConfigurationCustomizer
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor
import com.baomidou.mybatisplus.extension.plugins.inner.PaginationInnerInterceptor
import cn.esuny.orion.model.typehandler.PgUuidTypeHandler
import org.apache.ibatis.type.JdbcType
import org.mybatis.spring.annotation.MapperScan
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import java.util.UUID

/**
 * MyBatis-Plus 配置
 *
 * - 分页插件：支持 PostgreSQL 分页查询
 * - Mapper 扫描：自动注册 Mapper 接口
 */
@Configuration
@MapperScan("cn.esuny.orion.mapper")
class MyBatisPlusConfig {

    @Bean
    fun mybatisPlusInterceptor(): MybatisPlusInterceptor {
        val interceptor = MybatisPlusInterceptor()
        // 添加分页拦截器，并明确指定数据库为 PostgreSQL
        interceptor.addInnerInterceptor(PaginationInnerInterceptor(DbType.POSTGRE_SQL))
        return interceptor
    }

    @Bean
    fun uuidTypeHandlerCustomizer(): ConfigurationCustomizer = ConfigurationCustomizer { configuration ->
        configuration.typeHandlerRegistry.register(UUID::class.java, PgUuidTypeHandler::class.java)
        configuration.typeHandlerRegistry.register(UUID::class.java, JdbcType.OTHER, PgUuidTypeHandler::class.java)
    }
}
