package cn.esuny.orion.internal.nutrition

import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.LocalDate
import java.time.Period

@Service
class NutritionAiContextService(private val repository: NutritionAiContextQueryRepository) {
    @Transactional(readOnly = true)
    fun get(request: NutritionAiContextRequest): NutritionAiContextResponse {
        val snapshot = repository.load(request.subjectId)
        val profile = snapshot.profile
        val measurement = snapshot.latestMeasurement
        return NutritionAiContextResponse(
            subjectId = request.subjectId,
            ageYears = profile?.birthDate?.let { Period.between(it, LocalDate.now()).years },
            gender = profile?.gender?.name?.lowercase(),
            heightCm = measurement?.heightCm ?: profile?.heightCm,
            latestMeasurement = measurement?.let {
                MinimalMeasurement(it.measuredAt, it.heightCm, it.weightKg, it.bodyFatPercentage, it.waistCm)
            },
            activeGoals = snapshot.goals.map {
                MinimalGoal(it.goalType, it.targetWeightKg, it.targetBodyFatPercentage, it.priority, it.targetDate)
            },
            allergies = snapshot.allergies.map { MinimalAllergy(it.allergenCode, it.allergenName, it.severity) },
            medicalConditions = snapshot.conditions.map { MinimalCondition(it.conditionCode, it.conditionName) },
            dietaryRestrictions = snapshot.restrictions.map {
                MinimalRestriction(it.restrictionCode, it.restrictionName, it.category)
            },
            cuisinePreferences = snapshot.cuisines.map {
                MinimalCuisinePreference(it.cuisineCode, it.cuisineName, it.preferenceScore)
            },
        )
    }
}
