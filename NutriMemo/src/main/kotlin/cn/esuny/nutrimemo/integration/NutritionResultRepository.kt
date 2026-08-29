package cn.esuny.nutrimemo.integration

import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Repository
import java.time.LocalDate
import java.util.UUID

@Repository
class NutritionResultRepository(private val jdbc: JdbcTemplate) {
    fun startInbox(eventId: UUID, eventType: String, digest: String): Boolean = jdbc.query(
        """
        INSERT INTO nutri.integration_inbox(event_id,event_type,source_service,payload_sha256)
        VALUES(?,?,'HealthMind',?)
        ON CONFLICT(event_id) DO UPDATE SET status='processing',attempt_count=nutri.integration_inbox.attempt_count+1,last_error=NULL
        WHERE nutri.integration_inbox.status='failed'
        RETURNING event_id
        """.trimIndent(),
        { rs, _ -> rs.getObject(1, UUID::class.java) },
        eventId, eventType, digest,
    ).isNotEmpty()

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
             WHERE capture_session_id=? AND status IN ('ready_for_analysis','analysing','failed')
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
            "UPDATE nutri.meal_capture_sessions SET status='failed',failed_at=NOW() WHERE capture_session_id=? AND status IN ('ready_for_analysis','analysing')",
            meal.captureSessionId,
        )
        jdbc.update(
            "UPDATE nutri.meal_records SET analysis_status='failed' WHERE meal_id=? AND status='active' AND analysis_status<>'completed'",
            meal.mealId,
        )
    }

    fun completeInbox(eventId: UUID) {
        jdbc.update("UPDATE nutri.integration_inbox SET status='processed',processed_at=NOW() WHERE event_id=?", eventId)
    }

    fun failInbox(eventId: UUID, error: String) {
        jdbc.update(
            "UPDATE nutri.integration_inbox SET status='failed',last_error=? WHERE event_id=?",
            error.take(500), eventId,
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
}
