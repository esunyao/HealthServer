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
 *
 * 为什么要加这个配置？
 * 如果不加自定义配置，Spring 默认的 RedisTemplate 会使用 JDK 序列化（JdkSerializationRedisSerializer）。
 *
 * 默认方式的问题：在 Redis 客户端（如 Redis Insight、CLI）中查看 key 和 value 时，前面都会带有乱码般的二进制头（例如 \xac\xed\x00\x05t\x00\x04...），非常不直观且无法跨语言共享数据。
 * 当前配置的优势：
 * Key 可读性强：可以在 Redis 中直接通过 user:1001 这种纯文本查找 key。
 * Value 直观且类型安全：在 Redis 里直接显示为标准 JSON 字符串（如 {"id":1001,"name":"Tom"}），并且包含了类型信息，取出来时可以直接转换回对象。
 *
 */
@Configuration
class RedisConfig(private val objectMapper: ObjectMapper) {

    @Bean
    fun redisTemplate(connectionFactory: RedisConnectionFactory): RedisTemplate<String, Any> {
        // 创建序列化器
        val jsonSerializer = GenericJacksonJsonRedisSerializer(objectMapper)
        val stringSerializer = StringRedisSerializer()

        return RedisTemplate<String, Any>().apply {
            this.connectionFactory = connectionFactory
            keySerializer = stringSerializer         // 1. 普通 Key 序列化方式
            valueSerializer = jsonSerializer         // 2. 普通 Value 序列化方式
            hashKeySerializer = stringSerializer     // 3. Hash 结构的 Field/Key 序列化方式
            hashValueSerializer = jsonSerializer     // 4. Hash 结构的 Value 序列化方式
        }
    }
}
