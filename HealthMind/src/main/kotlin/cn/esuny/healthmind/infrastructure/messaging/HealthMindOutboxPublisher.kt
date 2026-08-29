package cn.esuny.healthmind.infrastructure.messaging

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import org.springframework.kafka.core.KafkaTemplate
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.transaction.annotation.Transactional
import java.util.UUID
import java.util.concurrent.TimeUnit

@Component
class HealthMindOutboxPublisher(
    private val jdbc: NamedParameterJdbcTemplate,
    private val kafka: KafkaTemplate<String, String>,
) {
    @Scheduled(fixedDelayString = "\${healthmind.scheduler.outbox-fixed-delay:PT1S}")
    fun publishNext() {
        val event = claim() ?: return
        try {
            kafka.send(event.destination, event.partitionKey, event.payload).get(15, TimeUnit.SECONDS)
            markPublished(event.eventId)
        } catch (exception: Exception) {
            markFailed(event.eventId, "KAFKA_PUBLISH_FAILED", "Kafka publish failed")
        }
    }

    @Transactional
    fun claim(): PendingEvent? {
        val row = jdbc.query(
            """
            SELECT event_id, destination_key, partition_key, payload::text
              FROM healthmind.integration_outbox
             WHERE status IN ('pending','failed') AND next_attempt_at<=NOW()
             ORDER BY created_at
             FOR UPDATE SKIP LOCKED LIMIT 1
            """.trimIndent(),
            emptyMap<String, Any>(),
        ) { rs, _ -> PendingEvent(rs.getObject(1, UUID::class.java), rs.getString(2), rs.getString(3), rs.getString(4)) }
            .singleOrNull() ?: return null
        jdbc.update(
            """
            UPDATE healthmind.integration_outbox
               SET status='publishing', attempt_count=attempt_count+1, failure_code=NULL, failure_message=NULL
             WHERE event_id=:eventId
            """.trimIndent(),
            mapOf("eventId" to row.eventId),
        )
        return row
    }

    @Transactional
    fun markPublished(eventId: UUID) {
        jdbc.update(
            "UPDATE healthmind.integration_outbox SET status='published', published_at=NOW() WHERE event_id=:eventId AND status='publishing'",
            mapOf("eventId" to eventId),
        )
    }

    @Transactional
    fun markFailed(eventId: UUID, code: String, message: String) {
        jdbc.update(
            """
            UPDATE healthmind.integration_outbox
               SET status='failed', failure_code=:code, failure_message=:message,
                   next_attempt_at=NOW() + LEAST(INTERVAL '5 minutes', INTERVAL '5 seconds' * power(2, LEAST(attempt_count, 6)))
             WHERE event_id=:eventId AND status='publishing'
            """.trimIndent(),
            mapOf("eventId" to eventId, "code" to code, "message" to message.take(500)),
        )
    }

    data class PendingEvent(val eventId: UUID, val destination: String, val partitionKey: String, val payload: String)
}
