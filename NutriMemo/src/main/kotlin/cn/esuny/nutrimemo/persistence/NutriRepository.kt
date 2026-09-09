package cn.esuny.nutrimemo.persistence

import cn.esuny.nutrimemo.model.*
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.core.RowMapper
import org.springframework.stereotype.Repository
import java.math.BigDecimal
import java.sql.ResultSet
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

internal data class MealSearchFilter(val whereClause: String, val parameters: List<Any>)

/**
 * 只为实际提供的筛选值增加占位符，避免 PostgreSQL 对 `? IS NULL` 的 null 参数无法推断类型。
 */
internal fun mealSearchFilter(userId: UUID, from: LocalDate, to: LocalDate, type: String?, keyword: String?): MealSearchFilter {
    val conditions = mutableListOf(
        "m.user_id=?",
        "m.status='active'",
        "m.local_date BETWEEN ? AND ?",
    )
    val parameters = mutableListOf<Any>(userId, from, to)
    type?.let {
        conditions += "m.meal_type=?"
        parameters += it
    }
    keyword?.let {
        conditions += "(m.notes ILIKE ? OR EXISTS(SELECT 1 FROM nutri.meal_items i WHERE i.meal_id=m.meal_id AND i.display_name ILIKE ?))"
        parameters += it
        parameters += it
    }
    return MealSearchFilter(conditions.joinToString(" AND "), parameters)
}

@Repository
class NutriRepository(private val jdbc: JdbcTemplate) {
    private val nutrientMapper = RowMapper { rs: ResultSet, _: Int -> NutrientDefinition(rs.getLong("nutrient_id"), rs.getString("nutrient_code"), rs.getString("nutrient_name"), rs.getString("unit"), rs.getBoolean("active")) }
    private val sessionMapper = RowMapper { rs: ResultSet, _: Int -> CaptureSessionRecord(rs.getObject("capture_session_id", UUID::class.java), rs.getObject("user_id", UUID::class.java), rs.getObject("client_request_id", UUID::class.java), rs.getString("status"), rs.getString("timezone"), rs.getInt("max_image_count"), rs.getObject("expires_at", OffsetDateTime::class.java), rs.getObject("analysis_requested_at", OffsetDateTime::class.java), rs.getObject("created_at", OffsetDateTime::class.java), rs.getObject("updated_at", OffsetDateTime::class.java)) }
    private val imageMapper = RowMapper { rs: ResultSet, _: Int -> CaptureImageRecord(rs.getLong("image_id"), rs.getObject("capture_session_id", UUID::class.java), rs.getInt("slot_no"), rs.getString("bucket"), rs.getString("object_key"), rs.getString("content_type"), rs.getLong("content_length"), rs.getObject("captured_at", OffsetDateTime::class.java), rs.getString("status"), rs.getObject("confirmed_at", OffsetDateTime::class.java), rs.getObject("created_at", OffsetDateTime::class.java)) }
    private val mealMapper = RowMapper { rs: ResultSet, _: Int -> MealRecord(rs.getLong("meal_id"), rs.getObject("capture_session_id", UUID::class.java), rs.getObject("user_id", UUID::class.java), rs.getString("meal_type"), rs.getObject("consumed_at", OffsetDateTime::class.java), rs.getString("timezone"), rs.getObject("local_date", LocalDate::class.java), rs.getString("notes"), rs.getString("analysis_status"), rs.getString("status"), rs.getObject("created_at", OffsetDateTime::class.java), rs.getObject("updated_at", OffsetDateTime::class.java)) }
    private val itemMapper = RowMapper { rs: ResultSet, _: Int -> MealItemRecord(rs.getLong("item_id"), rs.getLong("meal_id"), rs.getInt("sequence_no"), rs.getString("display_name"), rs.getBigDecimal("estimated_weight_g"), rs.getBigDecimal("confidence"), rs.getString("data_source"), rs.getBoolean("user_corrected"), rs.getString("notes")) }

    fun nutrientsByCodes(codes: Collection<String>): List<NutrientDefinition> = if (codes.isEmpty()) emptyList() else jdbc.query("SELECT nutrient_id,nutrient_code,nutrient_name,unit,active FROM nutri.nutrient_definitions WHERE nutrient_code IN (${codes.joinToString(",") { "?" }})", nutrientMapper, *codes.toTypedArray())

    fun session(id: UUID, userId: UUID) = jdbc.query("SELECT * FROM nutri.meal_capture_sessions WHERE capture_session_id=? AND user_id=?", sessionMapper, id, userId).firstOrNull()
    fun sessionForUpdate(id: UUID, userId: UUID) = jdbc.query("SELECT * FROM nutri.meal_capture_sessions WHERE capture_session_id=? AND user_id=? FOR UPDATE", sessionMapper, id, userId).firstOrNull()
    fun sessionByRequest(userId: UUID, requestId: UUID) = jdbc.query("SELECT * FROM nutri.meal_capture_sessions WHERE user_id=? AND client_request_id=?", sessionMapper, userId, requestId).firstOrNull()
    fun insertSession(value: CaptureSessionRecord) = jdbc.update("INSERT INTO nutri.meal_capture_sessions(capture_session_id,user_id,client_request_id,status,timezone,max_image_count,expires_at) VALUES(?,?,?,'created',?,?,?)", value.captureSessionId, value.userId, value.clientRequestId, value.timezone, value.maxImageCount, value.expiresAt)
    fun updateSessionStatus(id: UUID, userId: UUID, status: String, analysisRequested: Boolean = false) = jdbc.update("UPDATE nutri.meal_capture_sessions SET status=?,analysis_requested_at=CASE WHEN ? THEN NOW() ELSE analysis_requested_at END,failed_at=CASE WHEN ?='ready_for_analysis' THEN NULL ELSE failed_at END WHERE capture_session_id=? AND user_id=?", status, analysisRequested, status, id, userId)
    fun expiredSessions(now: OffsetDateTime) = jdbc.query("SELECT * FROM nutri.meal_capture_sessions WHERE expires_at < ? AND status IN ('created','uploading')", sessionMapper, now)
    fun expireSession(id: UUID) = jdbc.update("UPDATE nutri.meal_capture_sessions SET status='expired' WHERE capture_session_id=? AND status IN ('created','uploading')", id)
    fun cancelSession(id: UUID, userId: UUID) = jdbc.update("UPDATE nutri.meal_capture_sessions SET status='cancelled' WHERE capture_session_id=? AND user_id=? AND status IN ('created','uploading')", id, userId)

    fun images(sessionId: UUID) = jdbc.query("SELECT * FROM nutri.meal_capture_images WHERE capture_session_id=? ORDER BY slot_no", imageMapper, sessionId)
    fun image(id: Long, sessionId: UUID) = jdbc.query("SELECT * FROM nutri.meal_capture_images WHERE image_id=? AND capture_session_id=?", imageMapper, id, sessionId).firstOrNull()
    fun insertImage(value: CaptureImageRecord) = jdbc.update("INSERT INTO nutri.meal_capture_images(image_id,capture_session_id,slot_no,bucket,object_key,content_type,content_length,captured_at,status) VALUES(?,?,?,?,?,?,?,?, 'pending')", value.imageId, value.captureSessionId, value.slotNo, value.bucket, value.objectKey, value.contentType, value.contentLength, value.capturedAt)
    fun reuseDeletedImage(id: Long, key: String, contentType: String, contentLength: Long, capturedAt: OffsetDateTime?) = jdbc.update("UPDATE nutri.meal_capture_images SET object_key=?,content_type=?,content_length=?,captured_at=?,status='pending',confirmed_at=NULL,deleted_at=NULL,created_at=NOW() WHERE image_id=? AND status='deleted'", key, contentType, contentLength, capturedAt, id)
    fun confirmImage(id: Long) = jdbc.update("UPDATE nutri.meal_capture_images SET status='confirmed',confirmed_at=NOW() WHERE image_id=? AND status='pending'", id)
    fun deleteImage(id: Long) = jdbc.update("UPDATE nutri.meal_capture_images SET status='deleted',deleted_at=NOW() WHERE image_id=? AND status IN ('pending','confirmed')", id)
    fun expireImages(sessionId: UUID) = jdbc.update("UPDATE nutri.meal_capture_images SET status='expired',deleted_at=NOW() WHERE capture_session_id=? AND status IN ('pending','confirmed')", sessionId)
    fun confirmedImageCount(sessionId: UUID): Int = jdbc.queryForObject("SELECT COUNT(*) FROM nutri.meal_capture_images WHERE capture_session_id=? AND status='confirmed'", Int::class.javaObjectType, sessionId) ?: 0
    fun activeDraftCount(userId: UUID, now: OffsetDateTime): Int = jdbc.queryForObject("SELECT COUNT(*) FROM nutri.meal_capture_sessions WHERE user_id=? AND expires_at>? AND status IN ('created','uploading')", Int::class.javaObjectType, userId, now) ?: 0
    fun draftSessions(userId: UUID, now: OffsetDateTime): List<CaptureSessionRecord> = jdbc.query("SELECT * FROM nutri.meal_capture_sessions WHERE user_id=? AND expires_at>? AND status IN ('created','uploading') ORDER BY updated_at DESC", sessionMapper, userId, now)
    fun lockUserDrafts(userId: UUID) {
        jdbc.query("SELECT pg_advisory_xact_lock(hashtextextended(?::text, 0))", { _, _ -> Unit }, userId.toString())
    }

    fun insertOutbox(eventId: UUID, sessionId: UUID, mealId: Long, userId: UUID, traceId: String) = jdbc.update(
        """
        INSERT INTO nutri.integration_outbox(event_id,aggregate_id,event_type,payload)
        VALUES(?,?, 'nutrition.capture.ready.v1', jsonb_build_object(
            'event_id', CAST(? AS text),
            'event_type', 'nutrition.capture.ready.v1',
            'occurred_at', to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
            'producer', 'NutriMemo',
            'trace_id', CAST(? AS text),
            'subject_id', CAST(? AS text),
            'aggregate_type', 'meal',
            'aggregate_id', CAST(? AS text),
            'schema_version', '1.0',
            'payload', jsonb_build_object('capture_session_id', CAST(? AS text), 'meal_id', ?)
        ))
        """.trimIndent(),
        eventId, sessionId, eventId, traceId, userId, mealId, sessionId, mealId,
    )

    fun meal(id: Long, userId: UUID) = jdbc.query("SELECT * FROM nutri.meal_records WHERE meal_id=? AND user_id=?", mealMapper, id, userId).firstOrNull()
    fun mealForUpdate(id: Long, userId: UUID) = jdbc.query("SELECT * FROM nutri.meal_records WHERE meal_id=? AND user_id=? FOR UPDATE", mealMapper, id, userId).firstOrNull()
    fun mealByCaptureSession(sessionId: UUID, userId: UUID) = jdbc.query("SELECT * FROM nutri.meal_records WHERE capture_session_id=? AND user_id=?", mealMapper, sessionId, userId).firstOrNull()
    fun earliestConfirmedImageTime(sessionId: UUID) = jdbc.queryForObject("SELECT MIN(captured_at) FROM nutri.meal_capture_images WHERE capture_session_id=? AND status='confirmed' AND captured_at IS NOT NULL", OffsetDateTime::class.java, sessionId)
    fun insertMeal(value: MealRecord) = jdbc.update("INSERT INTO nutri.meal_records(meal_id,capture_session_id,user_id,meal_type,consumed_at,timezone,local_date,notes,analysis_status,status) VALUES(?,?,?,?,?,?,?,?,'queued','active')", value.mealId, value.captureSessionId, value.userId, value.mealType, value.consumedAt, value.timezone, value.localDate, value.notes)
    fun listMeals(userId: UUID, from: LocalDate, to: LocalDate, type: String?, keyword: String?, offset: Int, limit: Int): List<MealRecord> {
        val filter = mealSearchFilter(userId, from, to, type, keyword)
        return jdbc.query("SELECT m.* FROM nutri.meal_records m WHERE ${filter.whereClause} ORDER BY m.consumed_at DESC OFFSET ? LIMIT ?", mealMapper, *(filter.parameters + listOf(offset, limit)).toTypedArray())
    }
    fun countMeals(userId: UUID, from: LocalDate, to: LocalDate, type: String?, keyword: String?): Long {
        val filter = mealSearchFilter(userId, from, to, type, keyword)
        return jdbc.queryForObject("SELECT COUNT(*) FROM nutri.meal_records m WHERE ${filter.whereClause}", Long::class.javaObjectType, *filter.parameters.toTypedArray()) ?: 0
    }
    fun updateMeal(value: MealRecord) = jdbc.update("UPDATE nutri.meal_records SET meal_type=?,consumed_at=?,timezone=?,local_date=?,notes=?,analysis_status=? WHERE meal_id=? AND user_id=? AND status='active'", value.mealType, value.consumedAt, value.timezone, value.localDate, value.notes, value.analysisStatus, value.mealId, value.userId)
    fun updateMealAnalysisStatus(mealId: Long, userId: UUID, status: String) = jdbc.update("UPDATE nutri.meal_records SET analysis_status=? WHERE meal_id=? AND user_id=? AND status='active'", status, mealId, userId)
    fun deleteMeal(id: Long, userId: UUID) = jdbc.update("UPDATE nutri.meal_records SET status='deleted',deleted_at=NOW() WHERE meal_id=? AND user_id=? AND status='active'", id, userId)
    fun items(mealId: Long) = jdbc.query("SELECT * FROM nutri.meal_items WHERE meal_id=? ORDER BY sequence_no", itemMapper, mealId)
    fun itemNutrients(itemId: Long) = jdbc.query("SELECT nutrient_code_snapshot,nutrient_name_snapshot,unit_snapshot,amount FROM nutri.meal_item_nutrient_values WHERE item_id=? ORDER BY nutrient_code_snapshot", { rs, _ -> NutrientValue(rs.getString(1), rs.getString(2), rs.getString(3), rs.getBigDecimal(4)) }, itemId)
    fun mealNutrients(mealId: Long) = jdbc.query("SELECT nutrient_code_snapshot,nutrient_name_snapshot,unit_snapshot,total_amount FROM nutri.meal_nutrition_values WHERE meal_id=? ORDER BY nutrient_code_snapshot", { rs, _ -> NutrientValue(rs.getString(1), rs.getString(2), rs.getString(3), rs.getBigDecimal(4)) }, mealId)
    fun replaceItems(mealId: Long, items: List<MealItemRecord>, values: Map<Long, List<Pair<NutrientDefinition, BigDecimal>>>) {
        jdbc.update("DELETE FROM nutri.meal_items WHERE meal_id=?", mealId)
        items.forEach { item ->
            jdbc.update("INSERT INTO nutri.meal_items(item_id,meal_id,sequence_no,display_name,estimated_weight_g,confidence,data_source,user_corrected,notes) VALUES(?,?,?,?,?,NULL,'manual',true,?)", item.itemId, mealId, item.sequenceNo, item.displayName, item.estimatedWeightG, item.notes)
            values.getValue(item.itemId).forEach { (nutrient, amount) -> jdbc.update("INSERT INTO nutri.meal_item_nutrient_values(item_id,nutrient_id,nutrient_code_snapshot,nutrient_name_snapshot,unit_snapshot,amount,data_source,user_corrected) VALUES(?,?,?,?,?,?,'manual',true)", item.itemId, nutrient.nutrientId, nutrient.nutrientCode, nutrient.nutrientName, nutrient.unit, amount) }
        }
        jdbc.update("DELETE FROM nutri.meal_nutrition_values WHERE meal_id=?", mealId)
        jdbc.update("INSERT INTO nutri.meal_nutrition_values(meal_id,nutrient_id,nutrient_code_snapshot,nutrient_name_snapshot,unit_snapshot,total_amount) SELECT ?,v.nutrient_id,v.nutrient_code_snapshot,v.nutrient_name_snapshot,v.unit_snapshot,SUM(v.amount) FROM nutri.meal_item_nutrient_values v JOIN nutri.meal_items i ON i.item_id=v.item_id WHERE i.meal_id=? GROUP BY v.nutrient_id,v.nutrient_code_snapshot,v.nutrient_name_snapshot,v.unit_snapshot", mealId, mealId)
    }
    fun replaceAiItems(mealId: Long, items: List<MealItemRecord>, values: Map<Long, List<Pair<NutrientDefinition, BigDecimal>>>) {
        jdbc.update("DELETE FROM nutri.meal_items WHERE meal_id=?", mealId)
        items.forEach { item ->
            jdbc.update(
                "INSERT INTO nutri.meal_items(item_id,meal_id,sequence_no,display_name,estimated_weight_g,confidence,data_source,user_corrected,notes) VALUES(?,?,?,?,?,?,'ai',false,NULL)",
                item.itemId, mealId, item.sequenceNo, item.displayName, item.estimatedWeightG, item.confidence,
            )
            values.getValue(item.itemId).forEach { (nutrient, amount) ->
                jdbc.update(
                    "INSERT INTO nutri.meal_item_nutrient_values(item_id,nutrient_id,nutrient_code_snapshot,nutrient_name_snapshot,unit_snapshot,amount,data_source,user_corrected) VALUES(?,?,?,?,?,?,'ai',false)",
                    item.itemId, nutrient.nutrientId, nutrient.nutrientCode, nutrient.nutrientName, nutrient.unit, amount,
                )
            }
        }
        jdbc.update("DELETE FROM nutri.meal_nutrition_values WHERE meal_id=?", mealId)
        jdbc.update("INSERT INTO nutri.meal_nutrition_values(meal_id,nutrient_id,nutrient_code_snapshot,nutrient_name_snapshot,unit_snapshot,total_amount) SELECT ?,v.nutrient_id,v.nutrient_code_snapshot,v.nutrient_name_snapshot,v.unit_snapshot,SUM(v.amount) FROM nutri.meal_item_nutrient_values v JOIN nutri.meal_items i ON i.item_id=v.item_id WHERE i.meal_id=? GROUP BY v.nutrient_id,v.nutrient_code_snapshot,v.nutrient_name_snapshot,v.unit_snapshot", mealId, mealId)
    }
    fun recalculateDaily(userId: UUID, date: LocalDate, summaryId: Long) {
        val count = jdbc.queryForObject("SELECT COUNT(*) FROM nutri.meal_records WHERE user_id=? AND local_date=? AND status='active'", Int::class.javaObjectType, userId, date) ?: 0
        if (count == 0) { jdbc.update("DELETE FROM nutri.daily_nutrition_summaries WHERE user_id=? AND local_date=?", userId, date); return }
        jdbc.update("INSERT INTO nutri.daily_nutrition_summaries(summary_id,user_id,local_date,meal_count,last_recalculated_at) VALUES(?,?,?,?,NOW()) ON CONFLICT(user_id,local_date) DO UPDATE SET meal_count=EXCLUDED.meal_count,last_recalculated_at=NOW()", summaryId, userId, date, count)
        val id = jdbc.queryForObject("SELECT summary_id FROM nutri.daily_nutrition_summaries WHERE user_id=? AND local_date=?", Long::class.javaObjectType, userId, date)!!
        jdbc.update("DELETE FROM nutri.daily_nutrition_values WHERE summary_id=?", id)
        jdbc.update("INSERT INTO nutri.daily_nutrition_values(summary_id,nutrient_id,nutrient_code_snapshot,nutrient_name_snapshot,unit_snapshot,total_amount) SELECT ?,v.nutrient_id,v.nutrient_code_snapshot,v.nutrient_name_snapshot,v.unit_snapshot,SUM(v.total_amount) FROM nutri.meal_nutrition_values v JOIN nutri.meal_records m ON m.meal_id=v.meal_id WHERE m.user_id=? AND m.local_date=? AND m.status='active' GROUP BY v.nutrient_id,v.nutrient_code_snapshot,v.nutrient_name_snapshot,v.unit_snapshot", id, userId, date)
    }
    fun summaryRows(userId: UUID, date: LocalDate) = jdbc.query("SELECT s.meal_count,s.updated_at,v.nutrient_code_snapshot,v.nutrient_name_snapshot,v.unit_snapshot,v.total_amount FROM nutri.daily_nutrition_summaries s LEFT JOIN nutri.daily_nutrition_values v ON v.summary_id=s.summary_id WHERE s.user_id=? AND s.local_date=? ORDER BY v.nutrient_code_snapshot", { rs, _ -> arrayOf(rs.getInt(1), rs.getObject(2, OffsetDateTime::class.java), rs.getString(3), rs.getString(4), rs.getString(5), rs.getBigDecimal(6)) }, userId, date)
    fun breakdownRows(userId: UUID, date: LocalDate) = jdbc.query("SELECT m.meal_type,COUNT(DISTINCT m.meal_id),v.nutrient_code_snapshot,v.nutrient_name_snapshot,v.unit_snapshot,SUM(v.total_amount) FROM nutri.meal_records m JOIN nutri.meal_nutrition_values v ON v.meal_id=m.meal_id WHERE m.user_id=? AND m.local_date=? AND m.status='active' GROUP BY m.meal_type,v.nutrient_code_snapshot,v.nutrient_name_snapshot,v.unit_snapshot ORDER BY m.meal_type,v.nutrient_code_snapshot", { rs, _ -> arrayOf(rs.getString(1), rs.getInt(2), rs.getString(3), rs.getString(4), rs.getString(5), rs.getBigDecimal(6)) }, userId, date)
}
