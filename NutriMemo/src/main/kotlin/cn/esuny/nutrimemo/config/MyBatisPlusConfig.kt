package cn.esuny.nutrimemo.config

import com.baomidou.mybatisplus.annotation.DbType
import com.baomidou.mybatisplus.autoconfigure.ConfigurationCustomizer
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor
import com.baomidou.mybatisplus.extension.plugins.inner.PaginationInnerInterceptor
import cn.esuny.nutrimemo.persistence.PgUuidTypeHandler
import org.apache.ibatis.type.JdbcType
import org.mybatis.spring.annotation.MapperScan
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import java.util.UUID

@Configuration
@MapperScan("cn.esuny.nutrimemo.persistence")
class MyBatisPlusConfig {
    @Bean
    fun mybatisPlusInterceptor() = MybatisPlusInterceptor().apply {
        addInnerInterceptor(PaginationInnerInterceptor(DbType.POSTGRE_SQL))
    }

    @Bean
    fun uuidTypeHandlerCustomizer(): ConfigurationCustomizer = ConfigurationCustomizer {
        it.typeHandlerRegistry.register(UUID::class.java, PgUuidTypeHandler::class.java)
        it.typeHandlerRegistry.register(UUID::class.java, JdbcType.OTHER, PgUuidTypeHandler::class.java)
    }
}
