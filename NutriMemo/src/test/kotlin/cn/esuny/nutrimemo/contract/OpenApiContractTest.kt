package cn.esuny.nutrimemo.contract

import org.junit.jupiter.api.Test
import kotlin.test.assertContains
import kotlin.test.assertFalse

class OpenApiContractTest {
    @Test
    fun `OpenAPI documents capture session and history APIs without food library`() {
        val root = java.nio.file.Path.of(System.getProperty("user.dir"))
        val file = listOf(root.resolve("openapi.yaml"), root.resolve("NutriMemo/openapi.yaml")).first { java.nio.file.Files.exists(it) }
        val text = java.nio.file.Files.readString(file)
        listOf("/v1/nutri/capture-policy:", "/v1/nutri/capture-sessions:", "/submit:", "/retry:", "/v1/nutri/meals:", "MealCorrectionRequest", "X-Idempotency-Key").forEach { assertContains(text, it) }
        assertFalse(text.contains("/v1/nutri/foods:"))
        assertFalse(text.contains("/v1/nutri/custom-foods:"))
    }
}
