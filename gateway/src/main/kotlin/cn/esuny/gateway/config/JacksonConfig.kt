package cn.esuny.gateway.config

import com.fasterxml.jackson.annotation.JsonInclude
import com.fasterxml.jackson.databind.DeserializationFeature
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.SerializationFeature
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule
import com.fasterxml.jackson.module.kotlin.kotlinModule
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import java.text.SimpleDateFormat
import java.util.TimeZone

/**
 * Jackson JSON 序列化和反序列化配置类
 *
 * Spring Boot 默认使用 Jackson 作为处理 JSON 的工具。
 * 这里我们对 ObjectMapper（Jackson 的核心类）进行全局配置，
 * 比如统一时间的格式、忽略未知属性等，以便整个系统的 JSON 格式一致且更容错。
 */
@Configuration
class JacksonConfig {

    /**
     * 配置 ObjectMapper Bean，会替换 Spring 默认的设置。
     */
    @Bean
    fun objectMapper(): ObjectMapper {
        val mapper = ObjectMapper()
        
        // 1. 注册 Kotlin 模块
        // 这一步非常重要！如果不加，Jackson 将不知道如何处理 Kotlin 的 data class，
        // 也无法理解 Kotlin 里的非空类型和默认参数。
        mapper.registerModule(kotlinModule())
        
        // 2. 注册 JavaTimeModule
        // 支持 Java 8 的新日期类型，如 LocalDateTime, LocalDate 等。
        mapper.registerModule(JavaTimeModule())
        
        // 3. 配置日期格式为 ISO-8601 (yyyy-MM-dd HH:mm:ss)
        // 并关闭把日期写成时间戳的默认行为，这样输出的时间就是清晰的字符串。
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        mapper.dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss")
        mapper.setTimeZone(TimeZone.getTimeZone("GMT+8")) // 设定为东八区（北京时间）
        
        // 4. 反序列化时，遇到 JSON 里有但 Java/Kotlin 对象里没有的字段时不报错。
        // 这在对接外部系统或前端传递多余字段时非常有用，保证应用不会轻易崩溃。
        mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        
        // 5. 序列化时，不包含为 null 的字段
        // 这能减小 JSON 的体积，减少网络传输消耗，前端也会看着干净些。
        mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL)
        
        return mapper
    }
}
