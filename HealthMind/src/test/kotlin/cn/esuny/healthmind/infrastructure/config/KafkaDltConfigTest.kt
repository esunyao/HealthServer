package cn.esuny.healthmind.infrastructure.config

import io.mockk.mockk
import org.apache.kafka.clients.consumer.ConsumerRecord
import org.apache.kafka.common.TopicPartition
import org.junit.jupiter.api.Test
import org.springframework.boot.kafka.autoconfigure.ConcurrentKafkaListenerContainerFactoryConfigurer
import org.springframework.boot.kafka.autoconfigure.KafkaProperties
import org.springframework.kafka.core.ConsumerFactory
import org.springframework.kafka.core.KafkaTemplate
import org.springframework.kafka.listener.ContainerProperties
import org.springframework.kafka.listener.DefaultErrorHandler
import org.springframework.test.util.ReflectionTestUtils
import kotlin.test.assertEquals
import kotlin.test.assertIs

class KafkaDltConfigTest {
    @Test
    fun `custom factory preserves boot manual acknowledgement configuration`() {
        val configurer = configurer(ContainerProperties.AckMode.MANUAL)
        val factory = KafkaDltConfig().kafkaListenerContainerFactory(
            consumerFactory = mockk<ConsumerFactory<Any, Any>>(),
            kafkaTemplate = mockk<KafkaTemplate<String, String>>(relaxed = true),
            properties = HealthMindProperties(),
            configurer = configurer,
        )

        assertEquals(ContainerProperties.AckMode.MANUAL, factory.containerProperties.ackMode)
        assertIs<DefaultErrorHandler>(ReflectionTestUtils.getField(factory, "commonErrorHandler"))
    }

    @Test
    fun `dead letter destination follows the source partition`() {
        val record = ConsumerRecord<String, String>("nutrition-capture-ready", 2, 17L, "key", "value")

        assertEquals(
            TopicPartition("nutrition-capture-ready-dlt", 2),
            KafkaDltConfig().dltTopicPartition("nutrition-capture-ready-dlt", record),
        )
    }

    private fun configurer(ackMode: ContainerProperties.AckMode): ConcurrentKafkaListenerContainerFactoryConfigurer {
        val kafkaProperties = KafkaProperties().apply { listener.ackMode = ackMode }
        return ConcurrentKafkaListenerContainerFactoryConfigurer().also {
            ReflectionTestUtils.setField(it, "properties", kafkaProperties)
        }
    }
}
