package cn.esuny.nutrimemo.integration

import org.slf4j.LoggerFactory
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.kafka.core.KafkaTemplate
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.transaction.support.TransactionTemplate
import java.util.UUID
import java.util.concurrent.TimeUnit

@Component
class NutriOutboxPublisher(
    private val jdbc: JdbcTemplate,
    private val kafka: KafkaTemplate<String, String>,
    private val transactions: TransactionTemplate,
    private val properties: NutriIntegrationProperties,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    @Scheduled(fixedDelayString = "\${nutri.integration.outbox-fixed-delay:1s}")
    fun publishNext() {
        val event = transactions.execute { claim() } ?: return
        try {
            kafka.send(properties.captureReadyDestination, event.aggregateId.toString(), event.payload)
                .get(properties.publishTimeout.toMillis(), TimeUnit.MILLISECONDS)
            transactions.executeWithoutResult { markPublished(event.eventId) }
        } catch (_: Exception) {
            transactions.executeWithoutResult { markFailed(event.eventId) }
            log.warn("NutriMemo outbox event {} publish failed", event.eventId)
        }
    }

    @Scheduled(fixedDelayString = "\${nutri.integration.recovery-fixed-delay:1m}")
    fun recoverStalePublishing() {
        jdbc.update(
            """
            UPDATE nutri.integration_outbox
               SET status='failed', last_error='Recovered stale publisher', next_attempt_at=NOW(), locked_at=NULL
             WHERE status='publishing' AND locked_at < NOW() - INTERVAL '5 minutes'
            """.trimIndent(),
        )
    }

    private fun claim(): OutboxEvent? {
        val event = jdbc.query(
            """
            SELECT event_id, aggregate_id, payload::text
              FROM nutri.integration_outbox
             WHERE event_type='nutrition.capture.ready.v1' AND status IN ('pending','failed') AND next_attempt_at<=NOW()
             ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
            """.trimIndent(),
        ) { rs, _ -> OutboxEvent(rs.getObject(1, UUID::class.java), rs.getObject(2, UUID::class.java), rs.getString(3)) }
            .singleOrNull() ?: return null
        jdbc.update(
            "UPDATE nutri.integration_outbox SET status='publishing',attempt_count=attempt_count+1,locked_at=NOW(),last_error=NULL WHERE event_id=?",
            event.eventId,
        )
        return event
    }

    private fun markPublished(eventId: UUID) {
        jdbc.update(
            """
            WITH delivered AS (
                UPDATE nutri.integration_outbox
                   SET status='published',published_at=NOW(),locked_at=NULL
                 WHERE event_id=? AND status='publishing'
                RETURNING aggregate_id, (payload#>>'{payload,meal_id}')::bigint AS meal_id
            )
            UPDATE nutri.meal_capture_sessions s
               SET status='analysing'
              FROM delivered d
             WHERE s.capture_session_id=d.aggregate_id AND s.status='ready_for_analysis'
            """.trimIndent(),
            eventId,
        )
        jdbc.update(
            """
            UPDATE nutri.meal_records m SET analysis_status='analysing'
             WHERE m.meal_id=(SELECT (payload#>>'{payload,meal_id}')::bigint FROM nutri.integration_outbox WHERE event_id=?)
               AND m.status='active' AND m.analysis_status='queued'
            """.trimIndent(),
            eventId,
        )
    }

    private fun markFailed(eventId: UUID) {
        jdbc.update(
            """
            UPDATE nutri.integration_outbox
               SET status='failed',last_error='Kafka publish failed',locked_at=NULL,
                   next_attempt_at=NOW() + LEAST(INTERVAL '5 minutes', INTERVAL '5 seconds' * power(2, LEAST(attempt_count,6)))
             WHERE event_id=? AND status='publishing'
            """.trimIndent(),
            eventId,
        )
    }

    data class OutboxEvent(val eventId: UUID, val aggregateId: UUID, val payload: String)
}
