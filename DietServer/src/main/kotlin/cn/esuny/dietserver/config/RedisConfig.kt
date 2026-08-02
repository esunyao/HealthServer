package cn.esuny.dietserver.config

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
 */
@Configuration
class RedisConfig(private val objectMapper: ObjectMapper) {

    @Bean
    fun redisTemplate(connectionFactory: RedisConnectionFactory): RedisTemplate<String, Any> {
        val jsonSerializer = GenericJacksonJsonRedisSerializer(objectMapper)
        val stringSerializer = StringRedisSerializer()

        return RedisTemplate<String, Any>().apply {
            this.connectionFactory = connectionFactory
            keySerializer = stringSerializer         // Key 序列化
            valueSerializer = jsonSerializer         // Value 序列化
            hashKeySerializer = stringSerializer     // Hash Field 序列化
            hashValueSerializer = jsonSerializer     // Hash Value 序列化
        }
    }
}
