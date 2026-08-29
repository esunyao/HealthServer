package cn.esuny.orion.internal.nutrition

import cn.esuny.orion.mapper.UserAllergyMapper
import cn.esuny.orion.mapper.UserBodyMeasurementMapper
import cn.esuny.orion.mapper.UserConsentMapper
import cn.esuny.orion.mapper.UserCuisinePreferenceMapper
import cn.esuny.orion.mapper.UserDietaryRestrictionMapper
import cn.esuny.orion.mapper.UserHealthGoalMapper
import cn.esuny.orion.mapper.UserMedicalConditionMapper
import cn.esuny.orion.mapper.UserProfileMapper
import cn.esuny.orion.model.entity.user.UserAllergy
import cn.esuny.orion.model.entity.user.UserBodyMeasurement
import cn.esuny.orion.model.entity.user.UserConsent
import cn.esuny.orion.model.entity.user.UserCuisinePreference
import cn.esuny.orion.model.entity.user.UserDietaryRestriction
import cn.esuny.orion.model.entity.user.UserHealthGoal
import cn.esuny.orion.model.entity.user.UserMedicalCondition
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper
import org.springframework.stereotype.Repository
import java.time.LocalDate
import java.util.UUID

@Repository
class NutritionAiContextQueryRepository(
    private val profiles: UserProfileMapper,
    private val measurements: UserBodyMeasurementMapper,
    private val goals: UserHealthGoalMapper,
    private val allergies: UserAllergyMapper,
    private val conditions: UserMedicalConditionMapper,
    private val restrictions: UserDietaryRestrictionMapper,
    private val cuisines: UserCuisinePreferenceMapper,
    private val consents: UserConsentMapper,
) {
    fun load(subjectId: UUID): NutritionContextSnapshot {
        val consent = consents.selectList(QueryWrapper<UserConsent>()
            .eq("user_id", subjectId).eq("consent_type", CONSENT_TYPE)
            .orderByDesc("recorded_at").last("LIMIT 1")).singleOrNull()
        if (consent?.granted != true) throw AiNutritionConsentRequiredException()

        val today = LocalDate.now()
        return NutritionContextSnapshot(
            profile = profiles.selectByUserId(subjectId),
            latestMeasurement = measurements.selectList(QueryWrapper<UserBodyMeasurement>()
                .eq("user_id", subjectId).orderByDesc("measured_at").last("LIMIT 1")).singleOrNull(),
            goals = goals.selectList(QueryWrapper<UserHealthGoal>()
                .eq("user_id", subjectId).eq("status", "active").orderByAsc("priority")),
            allergies = allergies.selectList(QueryWrapper<UserAllergy>()
                .eq("user_id", subjectId).eq("active", true).orderByAsc("allergen_code")),
            conditions = conditions.selectList(QueryWrapper<UserMedicalCondition>()
                .eq("user_id", subjectId).eq("status", "active").orderByAsc("condition_code")),
            restrictions = restrictions.selectList(QueryWrapper<UserDietaryRestriction>()
                .eq("user_id", subjectId).eq("active", true)
                .and { it.isNull("starts_on").or().le("starts_on", today) }
                .and { it.isNull("ends_on").or().ge("ends_on", today) }
                .orderByAsc("restriction_code")),
            cuisines = cuisines.selectList(QueryWrapper<UserCuisinePreference>()
                .eq("user_id", subjectId).ne("preference_score", 0).orderByDesc("preference_score")),
        )
    }

    companion object {
        const val CONSENT_TYPE = "ai_nutrition_analysis"
    }
}

data class NutritionContextSnapshot(
    val profile: cn.esuny.orion.model.entity.user.UserProfile?,
    val latestMeasurement: UserBodyMeasurement?,
    val goals: List<UserHealthGoal>,
    val allergies: List<UserAllergy>,
    val conditions: List<UserMedicalCondition>,
    val restrictions: List<UserDietaryRestriction>,
    val cuisines: List<UserCuisinePreference>,
)

class AiNutritionConsentRequiredException : RuntimeException("AI nutrition analysis consent is required")
