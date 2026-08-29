package cn.esuny.orion.internal.nutrition

import cn.esuny.orion.model.entity.user.UserProfile
import io.mockk.every
import io.mockk.mockk
import java.time.LocalDate
import java.util.UUID
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class NutritionAiContextServiceTest {
    private val repository = mockk<NutritionAiContextQueryRepository>()
    private val service = NutritionAiContextService(repository)
    private val subjectId = UUID.randomUUID()
    private val request = NutritionAiContextRequest(subjectId, UUID.randomUUID())

    @Test
    fun `returns age without exposing birth date`() {
        every { repository.load(subjectId) } returns NutritionContextSnapshot(
            profile = UserProfile(userId = subjectId, birthDate = LocalDate.now().minusYears(30)),
            latestMeasurement = null,
            goals = emptyList(), allergies = emptyList(), conditions = emptyList(), restrictions = emptyList(), cuisines = emptyList(),
        )
        assertEquals(30, service.get(request).ageYears)
    }

    @Test
    fun `propagates consent required`() {
        every { repository.load(subjectId) } throws AiNutritionConsentRequiredException()
        assertFailsWith<AiNutritionConsentRequiredException> { service.get(request) }
    }
}
