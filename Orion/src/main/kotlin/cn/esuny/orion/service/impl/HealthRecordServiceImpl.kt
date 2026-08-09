package cn.esuny.orion.service.impl

import cn.esuny.orion.handler.BusinessException
import cn.esuny.orion.identity.AuthenticatedUser
import cn.esuny.orion.mapper.ClinicalObservationMapper
import cn.esuny.orion.mapper.UserAllergyMapper
import cn.esuny.orion.mapper.UserBodyMeasurementMapper
import cn.esuny.orion.mapper.UserConsentMapper
import cn.esuny.orion.mapper.UserCuisinePreferenceMapper
import cn.esuny.orion.mapper.UserDietaryRestrictionMapper
import cn.esuny.orion.mapper.UserHealthGoalMapper
import cn.esuny.orion.mapper.UserMedicalConditionMapper
import cn.esuny.orion.model.dto.user.AllergyRequest
import cn.esuny.orion.model.dto.user.BodyMeasurementRequest
import cn.esuny.orion.model.dto.user.ClinicalObservationRequest
import cn.esuny.orion.model.dto.user.DietaryRestrictionRequest
import cn.esuny.orion.model.dto.user.HealthGoalRequest
import cn.esuny.orion.model.dto.user.MedicalConditionRequest
import cn.esuny.orion.model.dto.user.ReplaceCuisinePreferencesRequest
import cn.esuny.orion.model.dto.user.UserConsentRequest
import cn.esuny.orion.model.entity.user.ClinicalObservation
import cn.esuny.orion.model.entity.user.UserAllergy
import cn.esuny.orion.model.entity.user.UserBodyMeasurement
import cn.esuny.orion.model.entity.user.UserConsent
import cn.esuny.orion.model.entity.user.UserCuisinePreference
import cn.esuny.orion.model.entity.user.UserDietaryRestriction
import cn.esuny.orion.model.entity.user.UserHealthGoal
import cn.esuny.orion.model.entity.user.UserMedicalCondition
import cn.esuny.orion.service.HealthRecordService
import cn.esuny.orion.service.SnowflakeIdGenerator
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import tools.jackson.databind.ObjectMapper
import java.time.OffsetDateTime
import java.util.UUID

@Service
class HealthRecordServiceImpl(
    private val ids: SnowflakeIdGenerator,
    private val measurementMapper: UserBodyMeasurementMapper,
    private val goalMapper: UserHealthGoalMapper,
    private val allergyMapper: UserAllergyMapper,
    private val conditionMapper: UserMedicalConditionMapper,
    private val restrictionMapper: UserDietaryRestrictionMapper,
    private val cuisineMapper: UserCuisinePreferenceMapper,
    private val observationMapper: ClinicalObservationMapper,
    private val consentMapper: UserConsentMapper,
    private val objectMapper: ObjectMapper
) : HealthRecordService {

    override fun listMeasurements(user: AuthenticatedUser) = measurementMapper.selectList(byUser(user.userId, "measured_at", false))
    override fun createMeasurement(user: AuthenticatedUser, request: BodyMeasurementRequest) = measurement(request, null, user.userId).also { measurementMapper.insert(it) }
    override fun updateMeasurement(user: AuthenticatedUser, id: Long, request: BodyMeasurementRequest): UserBodyMeasurement {
        val current = owned(measurementMapper.selectById(id), user.userId)
        val updated = measurement(request, current, user.userId).copy(measurementId = current.measurementId)
        measurementMapper.updateById(updated)
        return updated
    }
    override fun deleteMeasurement(user: AuthenticatedUser, id: Long) = measurementMapper.deleteById(owned(measurementMapper.selectById(id), user.userId).measurementId).let { Unit }

    override fun listGoals(user: AuthenticatedUser) = goalMapper.selectList(byUser(user.userId, "started_on", false))
    override fun createGoal(user: AuthenticatedUser, request: HealthGoalRequest) = goal(request, null, user.userId).also { goalMapper.insert(it) }
    override fun updateGoal(user: AuthenticatedUser, id: Long, request: HealthGoalRequest): UserHealthGoal {
        val current = owned(goalMapper.selectById(id), user.userId)
        val updated = goal(request, current, user.userId).copy(goalId = current.goalId)
        goalMapper.updateById(updated)
        return updated
    }
    override fun deleteGoal(user: AuthenticatedUser, id: Long) = goalMapper.deleteById(owned(goalMapper.selectById(id), user.userId).goalId).let { Unit }

    override fun listAllergies(user: AuthenticatedUser) = allergyMapper.selectList(byUser(user.userId, "created_at", false))
    override fun createAllergy(user: AuthenticatedUser, request: AllergyRequest) = allergy(request, null, user.userId).also { allergyMapper.insert(it) }
    override fun updateAllergy(user: AuthenticatedUser, id: Long, request: AllergyRequest): UserAllergy {
        val current = owned(allergyMapper.selectById(id), user.userId)
        val updated = allergy(request, current, user.userId).copy(allergyId = current.allergyId)
        allergyMapper.updateById(updated)
        return updated
    }
    override fun deleteAllergy(user: AuthenticatedUser, id: Long) = allergyMapper.deleteById(owned(allergyMapper.selectById(id), user.userId).allergyId).let { Unit }

    override fun listMedicalConditions(user: AuthenticatedUser) = conditionMapper.selectList(byUser(user.userId, "created_at", false))
    override fun createMedicalCondition(user: AuthenticatedUser, request: MedicalConditionRequest) = condition(request, null, user.userId).also { conditionMapper.insert(it) }
    override fun updateMedicalCondition(user: AuthenticatedUser, id: Long, request: MedicalConditionRequest): UserMedicalCondition {
        val current = owned(conditionMapper.selectById(id), user.userId)
        val updated = condition(request, current, user.userId).copy(conditionId = current.conditionId)
        conditionMapper.updateById(updated)
        return updated
    }
    override fun deleteMedicalCondition(user: AuthenticatedUser, id: Long) = conditionMapper.deleteById(owned(conditionMapper.selectById(id), user.userId).conditionId).let { Unit }

    override fun listDietaryRestrictions(user: AuthenticatedUser) = restrictionMapper.selectList(byUser(user.userId, "created_at", false))
    override fun createDietaryRestriction(user: AuthenticatedUser, request: DietaryRestrictionRequest) = restriction(request, null, user.userId).also { restrictionMapper.insert(it) }
    override fun updateDietaryRestriction(user: AuthenticatedUser, id: Long, request: DietaryRestrictionRequest): UserDietaryRestriction {
        val current = owned(restrictionMapper.selectById(id), user.userId)
        val updated = restriction(request, current, user.userId).copy(restrictionId = current.restrictionId)
        restrictionMapper.updateById(updated)
        return updated
    }
    override fun deleteDietaryRestriction(user: AuthenticatedUser, id: Long) = restrictionMapper.deleteById(owned(restrictionMapper.selectById(id), user.userId).restrictionId).let { Unit }

    override fun listCuisinePreferences(user: AuthenticatedUser) = cuisineMapper.selectList(byUser(user.userId, "preference_score", false))

    @Transactional
    override fun replaceCuisinePreferences(user: AuthenticatedUser, request: ReplaceCuisinePreferencesRequest): List<UserCuisinePreference> {
        if (request.preferences.map { it.cuisineCode.lowercase() }.distinct().size != request.preferences.size) {
            throw BusinessException(400, "菜系编码不能重复")
        }
        cuisineMapper.delete(byUser(user.userId, "user_id", true))
        val records = request.preferences.map {
            UserCuisinePreference(user.userId, it.cuisineCode, it.cuisineName, it.preferenceScore, it.notes)
        }
        records.forEach(cuisineMapper::insert)
        return records
    }

    override fun listObservations(user: AuthenticatedUser) = observationMapper.selectList(byUser(user.userId, "observed_at", false))
    override fun createObservation(user: AuthenticatedUser, request: ClinicalObservationRequest): ClinicalObservation {
        val numericPresent = request.valueNumeric != null
        val textPresent = !request.valueText.isNullOrBlank()
        if (numericPresent == textPresent) throw BusinessException(400, "数值结果和文本结果必须且只能填写一个")
        if (request.referenceHigh != null && request.referenceLow != null && request.referenceHigh < request.referenceLow) {
            throw BusinessException(400, "参考上限不能小于参考下限")
        }
        val metadata = request.metadata ?: "{}"
        val tree = runCatching { objectMapper.readTree(metadata) }.getOrElse {
            throw BusinessException(400, "metadata 必须是 JSON 对象")
        }
        if (!tree.isObject) throw BusinessException(400, "metadata 必须是 JSON 对象")
        return ClinicalObservation(
            ids.nextId(), user.userId, request.observationCode, request.observationName,
            request.valueNumeric, request.valueText?.takeIf(String::isNotBlank), request.unit,
            request.referenceLow, request.referenceHigh, request.interpretation ?: "unknown",
            request.observedAt ?: OffsetDateTime.now(), request.source ?: "self_reported",
            request.reportObjectKey, metadata
        ).also(observationMapper::insert)
    }

    override fun listConsents(user: AuthenticatedUser) = consentMapper.selectList(byUser(user.userId, "recorded_at", false))
    override fun createConsent(user: AuthenticatedUser, request: UserConsentRequest, clientIp: String?, userAgent: String?): UserConsent =
        UserConsent(ids.nextId(), user.userId, request.consentType, request.policyVersion, request.granted,
            source = request.source ?: "mobile", clientIp = clientIp, userAgent = userAgent?.take(500)).also(consentMapper::insert)

    private fun measurement(request: BodyMeasurementRequest, current: UserBodyMeasurement?, userId: UUID): UserBodyMeasurement {
        val result = UserBodyMeasurement(
            current?.measurementId ?: ids.nextId(), userId, request.measuredAt ?: current?.measuredAt ?: OffsetDateTime.now(),
            request.heightCm ?: current?.heightCm, request.weightKg ?: current?.weightKg,
            request.bodyFatPercentage ?: current?.bodyFatPercentage, request.waistCm ?: current?.waistCm,
            request.systolicBp ?: current?.systolicBp, request.diastolicBp ?: current?.diastolicBp,
            request.restingHeartRate ?: current?.restingHeartRate, request.source ?: current?.source ?: "manual",
            request.sourceReference ?: current?.sourceReference, request.notes ?: current?.notes,
            current?.createdAt ?: OffsetDateTime.now(), current?.updatedAt ?: OffsetDateTime.now()
        )
        if (listOf(result.heightCm, result.weightKg, result.bodyFatPercentage, result.waistCm, result.systolicBp, result.diastolicBp, result.restingHeartRate).all { it == null }) {
            throw BusinessException(400, "至少填写一个身体测量指标")
        }
        if (result.measuredAt.isAfter(OffsetDateTime.now().plusMinutes(5))) throw BusinessException(400, "测量时间不能晚于当前时间")
        return result
    }

    private fun goal(request: HealthGoalRequest, current: UserHealthGoal?, userId: UUID): UserHealthGoal {
        val startedOn = request.startedOn ?: current?.startedOn ?: java.time.LocalDate.now()
        val targetDate = request.targetDate ?: current?.targetDate
        if (targetDate != null && targetDate < startedOn) throw BusinessException(400, "目标日期不能早于开始日期")
        return UserHealthGoal(
            current?.goalId ?: ids.nextId(), userId, request.goalType, request.targetWeightKg ?: current?.targetWeightKg,
            request.targetBodyFatPercentage ?: current?.targetBodyFatPercentage, request.priority ?: current?.priority ?: 1,
            request.status ?: current?.status ?: "active", startedOn, targetDate,
            if ((request.status ?: current?.status) in setOf("achieved", "cancelled")) current?.completedAt ?: OffsetDateTime.now() else current?.completedAt,
            request.notes ?: current?.notes, current?.createdAt ?: OffsetDateTime.now(), current?.updatedAt ?: OffsetDateTime.now()
        )
    }

    private fun allergy(request: AllergyRequest, current: UserAllergy?, userId: UUID) = UserAllergy(
        current?.allergyId ?: ids.nextId(), userId, request.allergenCode, request.allergenName,
        request.severity ?: current?.severity, request.reactionDescription ?: current?.reactionDescription,
        request.diagnosisStatus ?: current?.diagnosisStatus ?: "self_reported", request.recordedOn ?: current?.recordedOn,
        request.active ?: current?.active ?: true, request.notes ?: current?.notes,
        current?.createdAt ?: OffsetDateTime.now(), current?.updatedAt ?: OffsetDateTime.now()
    )

    private fun condition(request: MedicalConditionRequest, current: UserMedicalCondition?, userId: UUID): UserMedicalCondition {
        val diagnosedOn = request.diagnosedOn ?: current?.diagnosedOn
        val resolvedOn = request.resolvedOn ?: current?.resolvedOn
        if (diagnosedOn != null && resolvedOn != null && resolvedOn < diagnosedOn) throw BusinessException(400, "结束日期不能早于诊断日期")
        return UserMedicalCondition(current?.conditionId ?: ids.nextId(), userId, request.conditionCode, request.conditionName,
            request.status ?: current?.status ?: "active", diagnosedOn, resolvedOn, request.source ?: current?.source ?: "self_reported",
            request.notes ?: current?.notes, current?.createdAt ?: OffsetDateTime.now(), current?.updatedAt ?: OffsetDateTime.now())
    }

    private fun restriction(request: DietaryRestrictionRequest, current: UserDietaryRestriction?, userId: UUID): UserDietaryRestriction {
        val startsOn = request.startsOn ?: current?.startsOn
        val endsOn = request.endsOn ?: current?.endsOn
        if (startsOn != null && endsOn != null && endsOn < startsOn) throw BusinessException(400, "结束日期不能早于开始日期")
        return UserDietaryRestriction(current?.restrictionId ?: ids.nextId(), userId, request.restrictionCode, request.restrictionName,
            request.category, request.source ?: current?.source ?: "self_reported", request.active ?: current?.active ?: true,
            startsOn, endsOn, request.notes ?: current?.notes, current?.createdAt ?: OffsetDateTime.now(), current?.updatedAt ?: OffsetDateTime.now())
    }

    private fun <T> byUser(userId: UUID, orderBy: String, ascending: Boolean) = QueryWrapper<T>()
        .eq("user_id", userId)
        .orderBy(true, ascending, orderBy)

    private fun <T> owned(record: T?, userId: UUID): T = when (record) {
        is UserBodyMeasurement -> record.takeIf { it.userId == userId }
        is UserHealthGoal -> record.takeIf { it.userId == userId }
        is UserAllergy -> record.takeIf { it.userId == userId }
        is UserMedicalCondition -> record.takeIf { it.userId == userId }
        is UserDietaryRestriction -> record.takeIf { it.userId == userId }
        else -> null
    } as T? ?: throw BusinessException(404, "记录不存在", HttpStatus.NOT_FOUND)
}
