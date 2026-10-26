package cn.esuny.nutrimemo.config

import org.junit.jupiter.api.Test
import kotlin.test.assertContains
import kotlin.test.assertFalse

class NutriMigrationScriptTest {
    private val reports = requireNotNull(
        javaClass.classLoader.getResource("db/migration/V3__persist_analysis_reports.sql"),
    ).readText()

    @Test
    fun `initial migration defines photo capture and dynamic nutrition tables`() {
        val sql = requireNotNull(javaClass.classLoader.getResource("db/migration/V1__create_nutri_data_collection.sql")).readText()
        listOf(
            "meal_capture_sessions", "meal_capture_images", "integration_outbox", "integration_inbox",
            "meal_records", "meal_items", "meal_item_nutrient_values", "meal_nutrition_values",
            "daily_nutrition_summaries", "daily_nutrition_values", "pg_trgm",
            "SODIUM", "VITAMIN_C", "analysis_status", "queued"
        ).forEach { assertContains(sql, it) }
        assertFalse(sql.contains("nutri.foods"))
        assertFalse(sql.contains("food_nutrient_values"))
        assertFalse(sql.contains("meal_item_nutrient_snapshots"))
        assertFalse(sql.contains("uq_outbox_capture_event"))
        assertContains(sql, "status IN ('created', 'uploading')")
    }

    @Test
    fun `analysis report migration adds review state ordering fields and dead letter audit`() {
        listOf(
            "needs_review",
            "meal_analysis_reports",
            "source_event_id",
            "event_occurred_at",
            "analysis_result_dead_letters",
            "payload_sha256",
            "failure_code",
        ).forEach { assertContains(reports, it) }
        assertContains(reports, "source_event_id UUID NOT NULL UNIQUE")
        assertContains(reports, "status IN ('completed', 'failed', 'needs_review')")
        assertContains(reports, "reason_code ~ '^[A-Z0-9_]{1,64}\$'")
    }
}
