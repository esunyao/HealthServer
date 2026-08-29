package cn.esuny.nutrimemo.integration

import org.apache.kafka.clients.consumer.ConsumerConfig
import org.apache.kafka.common.serialization.StringDeserializer
import org.apache.kafka.common.serialization.StringSerializer
import org.junit.jupiter.api.Test
import org.springframework.kafka.core.DefaultKafkaConsumerFactory
import org.springframework.kafka.core.DefaultKafkaProducerFactory
import org.springframework.kafka.core.KafkaTemplate
import org.springframework.kafka.test.EmbeddedKafkaBroker
import org.springframework.kafka.test.context.EmbeddedKafka
import org.springframework.kafka.test.utils.KafkaTestUtils
import java.time.Duration
import kotlin.test.assertEquals

@EmbeddedKafka(partitions = 1, topics = [NutritionKafkaContractTest.TOPIC])
class NutritionKafkaContractTest {
    @Test
    fun `preserves record key and snake case event payload`(broker: EmbeddedKafkaBroker) {
        val producer = DefaultKafkaProducerFactory<String, String>(
            KafkaTestUtils.producerProps(broker),
            StringSerializer(),
            StringSerializer(),
        )
        val consumerProperties = KafkaTestUtils.consumerProps("nutri-contract-test", "false", broker).apply {
            this[ConsumerConfig.AUTO_OFFSET_RESET_CONFIG] = "earliest"
        }
        val consumer = DefaultKafkaConsumerFactory(
            consumerProperties,
            StringDeserializer(),
            StringDeserializer(),
        ).createConsumer()
        try {
            broker.consumeFromAnEmbeddedTopic(consumer, TOPIC)
            val payload = """{"event_id":"68a8e352-e4bd-48dc-b886-d9257dfc62b2","event_type":"nutrition.capture.ready.v1","schema_version":"1.0","payload":{"capture_session_id":"4ca4bc97-276c-4cb4-ad08-547149114c06","meal_id":42}}"""

            KafkaTemplate(producer).send(TOPIC, "4ca4bc97-276c-4cb4-ad08-547149114c06", payload).get()
            val record = KafkaTestUtils.getSingleRecord(consumer, TOPIC, Duration.ofSeconds(10))

            assertEquals("4ca4bc97-276c-4cb4-ad08-547149114c06", record.key())
            assertEquals(payload, record.value())
        } finally {
            consumer.close()
            producer.destroy()
        }
    }

    companion object {
        const val TOPIC = "nutrition-capture-ready-contract-test"
    }
}
