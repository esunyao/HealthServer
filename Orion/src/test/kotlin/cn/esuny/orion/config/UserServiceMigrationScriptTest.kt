package cn.esuny.orion.config

import org.junit.jupiter.api.Test
import kotlin.test.assertContains
import kotlin.test.assertFalse

class UserServiceMigrationScriptTest {
    @Test
    fun `initial migration creates the complete normalized orion schema`() {
        val sql = requireNotNull(javaClass.classLoader.getResource("db/migration/V1__create_orion_user_service.sql"))
            .readText()
        listOf(
            "orion.users", "orion.user_profiles", "orion.user_body_measurements", "orion.user_health_goals",
            "orion.user_allergies", "orion.user_medical_conditions", "orion.user_dietary_restrictions",
            "orion.user_cuisine_preferences", "orion.clinical_observations", "orion.user_consents",
            "orion.file_cleanup_tasks", "uq_users_email_lower", "orion.set_updated_at"
        ).forEach { assertContains(sql, it) }
        assertFalse(sql.contains("\"User\""))
        assertFalse(sql.contains("password_hash"))
        assertFalse(sql.contains("refresh_tokens"))
    }
}
