package cn.esuny.orion.service

import cn.esuny.orion.identity.AuthenticatedUser
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

interface HealthRecordService {
    fun listMeasurements(user: AuthenticatedUser): List<UserBodyMeasurement>
    fun createMeasurement(user: AuthenticatedUser, request: BodyMeasurementRequest): UserBodyMeasurement
    fun updateMeasurement(user: AuthenticatedUser, id: Long, request: BodyMeasurementRequest): UserBodyMeasurement
    fun deleteMeasurement(user: AuthenticatedUser, id: Long)
    fun listGoals(user: AuthenticatedUser): List<UserHealthGoal>
    fun createGoal(user: AuthenticatedUser, request: HealthGoalRequest): UserHealthGoal
    fun updateGoal(user: AuthenticatedUser, id: Long, request: HealthGoalRequest): UserHealthGoal
    fun deleteGoal(user: AuthenticatedUser, id: Long)
    fun listAllergies(user: AuthenticatedUser): List<UserAllergy>
    fun createAllergy(user: AuthenticatedUser, request: AllergyRequest): UserAllergy
    fun updateAllergy(user: AuthenticatedUser, id: Long, request: AllergyRequest): UserAllergy
    fun deleteAllergy(user: AuthenticatedUser, id: Long)
    fun listMedicalConditions(user: AuthenticatedUser): List<UserMedicalCondition>
    fun createMedicalCondition(user: AuthenticatedUser, request: MedicalConditionRequest): UserMedicalCondition
    fun updateMedicalCondition(user: AuthenticatedUser, id: Long, request: MedicalConditionRequest): UserMedicalCondition
    fun deleteMedicalCondition(user: AuthenticatedUser, id: Long)
    fun listDietaryRestrictions(user: AuthenticatedUser): List<UserDietaryRestriction>
    fun createDietaryRestriction(user: AuthenticatedUser, request: DietaryRestrictionRequest): UserDietaryRestriction
    fun updateDietaryRestriction(user: AuthenticatedUser, id: Long, request: DietaryRestrictionRequest): UserDietaryRestriction
    fun deleteDietaryRestriction(user: AuthenticatedUser, id: Long)
    fun listCuisinePreferences(user: AuthenticatedUser): List<UserCuisinePreference>
    fun replaceCuisinePreferences(user: AuthenticatedUser, request: ReplaceCuisinePreferencesRequest): List<UserCuisinePreference>
    fun listObservations(user: AuthenticatedUser): List<ClinicalObservation>
    fun createObservation(user: AuthenticatedUser, request: ClinicalObservationRequest): ClinicalObservation
    fun listConsents(user: AuthenticatedUser): List<UserConsent>
    fun createConsent(user: AuthenticatedUser, request: UserConsentRequest, clientIp: String?, userAgent: String?): UserConsent
}
