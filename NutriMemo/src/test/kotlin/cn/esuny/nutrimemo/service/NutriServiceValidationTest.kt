package cn.esuny.nutrimemo.service

import cn.esuny.nutrimemo.config.OssProperties
import cn.esuny.nutrimemo.handler.BusinessException
import cn.esuny.nutrimemo.identity.AuthenticatedUser
import cn.esuny.nutrimemo.model.MealItemInput
import cn.esuny.nutrimemo.model.MealUpsertRequest
import cn.esuny.nutrimemo.persistence.NutriRepository
import io.mockk.every
import io.mockk.mockk
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import java.math.BigDecimal
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertEquals

class NutriServiceValidationTest {
    private val repository = mockk<NutriRepository>()
    private val service = NutriService(
        repository, SnowflakeIdGenerator(), mockk<S3Client>(), mockk<S3Presigner>(),
        OssProperties("https://storage.example", "https://storage.example", "a", "s", "nutri")
    )
    private val user = AuthenticatedUser(UUID.randomUUID())

    @Test
    fun `rejects invalid IANA timezone before persistence`() {
        every { repository.mealByIdempotency(any(), any()) } returns null
        val exception = assertThrows<BusinessException> { service.createMeal(user, UUID.randomUUID(), request(timezone = "CST")) }
        assertEquals(400, exception.code)
    }

    @Test
    fun `rejects duplicate food in one meal before persistence`() {
        every { repository.mealByIdempotency(any(), any()) } returns null
        val item = MealItemInput(1, BigDecimal("50"))
        val exception = assertThrows<BusinessException> { service.createMeal(user, UUID.randomUUID(), request(items = listOf(item, item))) }
        assertEquals(400, exception.code)
    }

    private fun request(timezone: String = "Asia/Shanghai", items: List<MealItemInput> = listOf(MealItemInput(1, BigDecimal("50")))) =
        MealUpsertRequest("breakfast", OffsetDateTime.now().minusHours(1), timezone, entrySource = "manual", items = items)
}
