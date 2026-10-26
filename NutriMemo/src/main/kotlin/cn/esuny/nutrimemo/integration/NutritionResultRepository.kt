package cn.esuny.nutrimemo.integration

import cn.esuny.nutrimemo.model.MealAnalysisReportRecord
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Repository
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

@Repository
class NutritionResultRepository(private val jdbc: JdbcTemplate) {
    fun startInbox(eventId: UUID, eventType: String, digest: String): Boolean {
        val inserted = jdbc.query(
            """
            INSERT INTO nutri.integration_inbox(event_id,event_type,source_service,payload_sha256)
            VALUES(?,?,'HealthMind',?)
            ON CONFLICT(event_id) DO NOTHING
            RETURNING event_id
            """.trimIndent(),
            { rs, _ -> rs.getObject(1, UUID::class.java) },
            eventId, eventType, digest,
        ).isNotEmpty()
        if (inserted) return true

        val existing = jdbc.query(
            "SELECT payload_sha256,status FROM nutri.integration_inbox WHERE event_id=? FOR UPDATE",
            { rs, _ -> ExistingInbox(rs.getString("payload_sha256"), rs.getString("status")) },
            eventId,
        ).singleOrNull() ?: return false
        if (existing.digest.trim() != digest) {
            throw UnrecoverableResultEventException(
                "EVENT_IDEMPOTENCY_CONFLICT",
                "Integration event ID was reused with different content",
            )
        }
        if (existing.status != "failed") return false

        jdbc.update(
            """
            UPDATE nutri.integration_inbox
               SET event_type=?,status='processing',attempt_count=attempt_count+1,last_error=NULL
             WHERE event_id=? AND status='failed'
            """.trimIndent(),
            eventType,
            eventId,
        )
        return true
    }

    fun lockMeal(captureSessionId: UUID, mealId: Long): ResultMeal? = jdbc.query(
        """
        SELECT meal_id,capture_session_id,user_id,local_date,analysis_status,status
          FROM nutri.meal_records
         WHERE meal_id=? AND capture_session_id=? FOR UPDATE
        """.trimIndent(),
        { rs, _ ->
            ResultMeal(
                rs.getLong("meal_id"),
                rs.getObject("capture_session_id", UUID::class.java),
                rs.getObject("user_id", UUID::class.java),
                rs.getObject("local_date", LocalDate::class.java),
                rs.getString("analysis_status"),
                rs.getString("status"),
            )
        },
        mealId, captureSessionId,
    ).singleOrNull()

    fun hasManualOrCorrectedItems(mealId: Long): Boolean = jdbc.queryForObject(
        "SELECT EXISTS(SELECT 1 FROM nutri.meal_items WHERE meal_id=? AND (data_source='manual' OR user_corrected))",
        Boolean::class.javaObjectType,
        mealId,
    ) == true

    fun markCompleted(meal: ResultMeal, updateMeal: Boolean) {
        jdbc.update(
            """
            UPDATE nutri.meal_capture_sessions SET status='completed',completed_at=NOW(),failed_at=NULL
             WHERE capture_session_id=? AND status IN ('ready_for_analysis','analysing','needs_review','failed')
            """.trimIndent(),
            meal.captureSessionId,
        )
        if (updateMeal) {
            jdbc.update(
                "UPDATE nutri.meal_records SET analysis_status='completed' WHERE meal_id=? AND status='active'",
                meal.mealId,
            )
        }
    }

    fun markFailed(meal: ResultMeal) {
        jdbc.update(
            "UPDATE nutri.meal_capture_sessions SET status='failed',failed_at=NOW() WHERE capture_session_id=? AND status IN ('ready_for_analysis','analysing','needs_review')",
            meal.captureSessionId,
        )
        jdbc.update(
            "UPDATE nutri.meal_records SET analysis_status='failed' WHERE meal_id=? AND status='active' AND analysis_status<>'completed'",
            meal.mealId,
        )
    }

    fun markNeedsReview(meal: ResultMeal) {
        jdbc.update(
            "UPDATE nutri.meal_capture_sessions SET status='needs_review',failed_at=NULL WHERE capture_session_id=? AND status IN ('ready_for_analysis','analysing','failed')",
            meal.captureSessionId,
        )
        jdbc.update(
            "UPDATE nutri.meal_records SET analysis_status='needs_review' WHERE meal_id=? AND status='active' AND analysis_status<>'completed'",
            meal.mealId,
        )
    }

    fun saveReport(report: MealAnalysisReportRecord): Boolean = jdbc.query(
        """
        INSERT INTO nutri.meal_analysis_reports
            (meal_id,task_id,source_event_id,event_occurred_at,status,overall_confidence,result_version,
             reason_code,reason_message,analyzed_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(meal_id) DO UPDATE
           SET task_id=EXCLUDED.task_id,
               source_event_id=EXCLUDED.source_event_id,
               event_occurred_at=EXCLUDED.event_occurred_at,
               status=EXCLUDED.status,
               overall_confidence=EXCLUDED.overall_confidence,
               result_version=EXCLUDED.result_version,
               reason_code=EXCLUDED.reason_code,
               reason_message=EXCLUDED.reason_message,
               analyzed_at=EXCLUDED.analyzed_at,
               updated_at=NOW()
         WHERE meal_analysis_reports.source_event_id=EXCLUDED.source_event_id
            OR meal_analysis_reports.event_occurred_at < EXCLUDED.event_occurred_at
        RETURNING meal_id
        """.trimIndent(),
        { rs, _ -> rs.getLong(1) },
        report.mealId,
        report.taskId,
        report.sourceEventId,
        report.eventOccurredAt,
        report.status,
        report.overallConfidence,
        report.resultVersion,
        report.reasonCode,
        report.reasonMessage,
        report.analyzedAt,
    ).isNotEmpty()

    fun completeInbox(eventId: UUID) {
        jdbc.update("UPDATE nutri.integration_inbox SET status='processed',processed_at=NOW() WHERE event_id=?", eventId)
    }

    fun failInbox(eventId: UUID, error: String) {
        jdbc.update(
            "UPDATE nutri.integration_inbox SET status='failed',last_error=? WHERE event_id=?",
            error.take(500), eventId,
        )
    }

    fun recordDeadLetter(
        eventId: UUID?,
        eventType: String?,
        mealId: Long?,
        payloadDigest: String,
        rawPayload: String,
        failureCode: String,
        failureMessage: String,
    ) {
        jdbc.update(
            """
            INSERT INTO nutri.analysis_result_dead_letters
                (event_id,event_type,attempted_meal_id,payload_sha256,raw_payload,failure_code,failure_message)
            VALUES(?,?,?,?,?,?,?)
            """.trimIndent(),
            eventId,
            eventType?.take(100),
            mealId,
            payloadDigest,
            rawPayload,
            failureCode.take(64),
            failureMessage.take(1000),
        )
    }

    data class ResultMeal(
        val mealId: Long,
        val captureSessionId: UUID,
        val userId: UUID,
        val localDate: LocalDate,
        val analysisStatus: String,
        val status: String,
    )

    private data class ExistingInbox(val digest: String, val status: String)
}
