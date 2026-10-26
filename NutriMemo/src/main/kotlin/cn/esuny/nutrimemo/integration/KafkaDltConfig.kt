package cn.esuny.nutrimemo.integration

import org.apache.kafka.common.TopicPartition
import org.apache.kafka.clients.consumer.ConsumerRecord
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.boot.kafka.autoconfigure.ConcurrentKafkaListenerContainerFactoryConfigurer
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory
import org.springframework.kafka.core.ConsumerFactory
import org.springframework.kafka.core.KafkaTemplate
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer
import org.springframework.kafka.listener.DefaultErrorHandler
import org.springframework.util.backoff.FixedBackOff

@Configuration
class KafkaDltConfig {
    @Bean
    fun kafkaListenerContainerFactory(
        consumerFactory: ConsumerFactory<Any, Any>,
        kafkaTemplate: KafkaTemplate<String, String>,
        properties: NutriIntegrationProperties,
        configurer: ConcurrentKafkaListenerContainerFactoryConfigurer,
    ): ConcurrentKafkaListenerContainerFactory<Any, Any> {
        val recoverer = DeadLetterPublishingRecoverer(kafkaTemplate) { record, _ ->
            dltTopicPartition(properties.analysisResultDltDestination, record)
        }
        val factory = ConcurrentKafkaListenerContainerFactory<Any, Any>()
        val errorHandler = DefaultErrorHandler(recoverer, FixedBackOff(1_000L, 5L)).apply {
            addNotRetryableExceptions(UnrecoverableResultEventException::class.java)
        }
        configure(
            factory,
            consumerFactory,
            configurer,
            errorHandler,
        )
        return factory
    }

    fun configure(
        factory: ConcurrentKafkaListenerContainerFactory<Any, Any>,
        consumerFactory: ConsumerFactory<Any, Any>,
        configurer: ConcurrentKafkaListenerContainerFactoryConfigurer,
        errorHandler: DefaultErrorHandler,
    ) {
        configurer.configure(factory, consumerFactory)
        factory.setCommonErrorHandler(errorHandler)
    }

    internal fun dltTopicPartition(destination: String, record: ConsumerRecord<*, *>): TopicPartition =
        TopicPartition(destination, record.partition())
}
