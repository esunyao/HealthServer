package cn.esuny.orion.config

import com.baomidou.mybatisplus.annotation.DbType
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor
import com.baomidou.mybatisplus.extension.plugins.inner.PaginationInnerInterceptor
import org.mybatis.spring.annotation.MapperScan
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

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
}
