package cn.esuny.nutrimemo.config

import org.junit.jupiter.api.Test
import kotlin.test.assertContains
import kotlin.test.assertFalse

class NutriMigrationScriptTest {
    @Test
    fun `initial migration creates the complete isolated nutri schema`() {
        val sql = requireNotNull(javaClass.classLoader.getResource("db/migration/V1__create_nutri_data_collection.sql")).readText()
        listOf(
            "CREATE SCHEMA IF NOT EXISTS nutri", "nutri.nutrient_definitions", "nutri.foods", "nutri.food_nutrient_values",
            "nutri.food_aliases", "nutri.meal_records", "nutri.meal_items", "nutri.meal_item_nutrient_snapshots",
            "nutri.meal_images", "nutri.daily_nutrition_summaries", "nutri.daily_nutrition_values", "uq_meals_user_idempotency",
            "ENERGY_KCAL", "PROTEIN", "FAT", "CARBOHYDRATE"
        ).forEach { assertContains(sql, it) }
        assertFalse(sql.contains("orion."))
        assertFalse(sql.contains("password_hash"))
        assertFalse(sql.contains("refresh_tokens"))
    }
}
