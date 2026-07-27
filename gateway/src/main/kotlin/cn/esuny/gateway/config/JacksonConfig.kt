package cn.esuny.gateway.config

import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

import tools.jackson.databind.DeserializationFeature
import tools.jackson.databind.cfg.DateTimeFeature
import java.util.TimeZone

/**
 * Jackson JSON 序列化和反序列化配置类
 *
 * Spring Boot 4.1 默认使用 Jackson 3 作为 JSON 处理工具。
 * Jackson 3 的核心类是不可变的 JsonMapper（替代了旧版的 ObjectMapper），
 * 通过 JsonMapperBuilderCustomizer 来定制全局行为。
 *
 * 注意：Jackson 3 的包名从 com.fasterxml.jackson 改成了 tools.jackson，
 * 但注解包（@JsonInclude 等）仍然保留在 com.fasterxml.jackson.annotation 下。
 */
@Configuration
class JacksonConfig {

    /**
     * 通过 JsonMapperBuilderCustomizer 定制全局 JSON 行为
     *
     * Spring Boot 4.1 会自动收集所有 JsonMapperBuilderCustomizer Bean，
     * 依次应用到 JsonMapper 的构建过程中。这是 Jackson 3 推荐的配置方式。
     */
    @Bean
    fun jacksonCustomizer(): JsonMapperBuilderCustomizer {
        return JsonMapperBuilderCustomizer { builder ->
            // 1. 关闭将日期写成时间戳的行为，输出清晰的字符串格式
            builder.disable(DateTimeFeature.WRITE_DATES_AS_TIMESTAMPS)

            // 2. 反序列化时，遇到 JSON 里有但对象里没有的字段不报错
            //    对接外部系统或前端传多余字段时非常有用
            builder.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)

            // 3. 设定时区为东八区（北京时间）
            builder.defaultTimeZone(TimeZone.getTimeZone("GMT+8"))
        }
    }
}
