package cn.esuny.orion.config

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.data.redis.connection.RedisConnectionFactory
import org.springframework.data.redis.core.RedisTemplate
import org.springframework.data.redis.serializer.GenericJacksonJsonRedisSerializer
import org.springframework.data.redis.serializer.StringRedisSerializer
import tools.jackson.databind.ObjectMapper

/**
 * Redis 配置
 *
 * 使用 GenericJacksonJsonRedisSerializer（Spring Data Redis 4.x 推荐）替代 JDK 序列化，
 * 存入 Redis 的数据人类可读，且不受类版本变更影响。
 *
 * Spring Boot 4.x + Spring Data Redis 4.x 均使用 Jackson 3.x（tools.jackson），
 * 注入 Spring 自动配置的 ObjectMapper 即可。
 */
@Configuration
class RedisConfig(private val objectMapper: ObjectMapper) {

    @Bean
    fun redisTemplate(connectionFactory: RedisConnectionFactory): RedisTemplate<String, Any> {
        val jsonSerializer = GenericJacksonJsonRedisSerializer(objectMapper)
        val stringSerializer = StringRedisSerializer()

        return RedisTemplate<String, Any>().apply {
            this.connectionFactory = connectionFactory
            keySerializer = stringSerializer
            valueSerializer = jsonSerializer
            hashKeySerializer = stringSerializer
            hashValueSerializer = jsonSerializer
        }
    }
}
