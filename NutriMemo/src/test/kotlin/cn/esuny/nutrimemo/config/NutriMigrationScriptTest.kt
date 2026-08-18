package cn.esuny.nutrimemo.config

import org.junit.jupiter.api.Test
import kotlin.test.assertContains
import kotlin.test.assertFalse

class NutriMigrationScriptTest {
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
}
