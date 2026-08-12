package cn.esuny.nutrimemo.contract

import org.junit.jupiter.api.Test
import kotlin.test.assertContains

class OpenApiContractTest {
    @Test
    fun `OpenAPI documents every implemented NutriMemo endpoint and security boundary`() {
        // The OpenAPI document is intentionally located at the module root for Apifox import.
        val root = java.nio.file.Path.of(System.getProperty("user.dir"))
        val file = listOf(root.resolve("openapi.yaml"), root.resolve("NutriMemo/openapi.yaml")).firstOrNull { java.nio.file.Files.exists(it) }
            ?: error("NutriMemo openapi.yaml not found from $root")
        val text = java.nio.file.Files.readString(file)
        listOf("openapi: 3.1.0", "/v1/nutri/foods:", "/v1/nutri/custom-foods:", "/v1/nutri/meals:", "/v1/nutri/meals/{mealId}/images/presign:", "/v1/nutri/summaries/daily:", "bearerAuth", "X-Idempotency-Key").forEach { assertContains(text, it) }
    }
}
