package cn.esuny.gateway.config

import com.fasterxml.jackson.databind.DeserializationFeature
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.SerializationFeature
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import java.util.TimeZone

/**
 * Jackson JSON 序列化和反序列化配置类
 *
 * 配置全局 JSON 行为：
 * - 日期不转时间戳
 * - 忽略未知属性
 * - 时区 GMT+8
 */
@Configuration
class JacksonConfig {

    @Bean
    fun objectMapper(): ObjectMapper {
        val mapper = ObjectMapper()

        // 1. 关闭将日期写成时间戳的行为
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)

        // 2. 反序列化时，遇到 JSON 里有但对象里没有的字段不报错
        mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)

        // 3. 设定时区为东八区（北京时间）
        mapper.setTimeZone(TimeZone.getTimeZone("GMT+8"))

        return mapper
    }
}
