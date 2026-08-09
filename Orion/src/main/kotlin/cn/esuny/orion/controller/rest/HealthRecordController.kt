package cn.esuny.orion.controller.rest

import cn.esuny.orion.identity.AuthenticatedUser
import cn.esuny.orion.identity.CurrentUser
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
import cn.esuny.orion.model.result.ApiResponse
import cn.esuny.orion.service.HealthRecordService
import jakarta.servlet.http.HttpServletRequest
import jakarta.validation.Valid
import org.springframework.web.bind.annotation.DeleteMapping
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PatchMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/v1/users/self")
class HealthRecordController(private val healthRecordService: HealthRecordService) {
    @GetMapping("/body-measurements") fun measurements(@CurrentUser user: AuthenticatedUser): ApiResponse<List<UserBodyMeasurement>> = ApiResponse.success(data = healthRecordService.listMeasurements(user))
    @PostMapping("/body-measurements") fun createMeasurement(@CurrentUser user: AuthenticatedUser, @RequestBody @Valid request: BodyMeasurementRequest): ApiResponse<UserBodyMeasurement> = ApiResponse.success(data = healthRecordService.createMeasurement(user, request))
    @PatchMapping("/body-measurements/{id}") fun updateMeasurement(@CurrentUser user: AuthenticatedUser, @PathVariable id: Long, @RequestBody @Valid request: BodyMeasurementRequest): ApiResponse<UserBodyMeasurement> = ApiResponse.success(data = healthRecordService.updateMeasurement(user, id, request))
    @DeleteMapping("/body-measurements/{id}") fun deleteMeasurement(@CurrentUser user: AuthenticatedUser, @PathVariable id: Long): ApiResponse<Unit> = delete { healthRecordService.deleteMeasurement(user, id) }

    @GetMapping("/health-goals") fun goals(@CurrentUser user: AuthenticatedUser): ApiResponse<List<UserHealthGoal>> = ApiResponse.success(data = healthRecordService.listGoals(user))
    @PostMapping("/health-goals") fun createGoal(@CurrentUser user: AuthenticatedUser, @RequestBody @Valid request: HealthGoalRequest): ApiResponse<UserHealthGoal> = ApiResponse.success(data = healthRecordService.createGoal(user, request))
    @PatchMapping("/health-goals/{id}") fun updateGoal(@CurrentUser user: AuthenticatedUser, @PathVariable id: Long, @RequestBody @Valid request: HealthGoalRequest): ApiResponse<UserHealthGoal> = ApiResponse.success(data = healthRecordService.updateGoal(user, id, request))
    @DeleteMapping("/health-goals/{id}") fun deleteGoal(@CurrentUser user: AuthenticatedUser, @PathVariable id: Long): ApiResponse<Unit> = delete { healthRecordService.deleteGoal(user, id) }

    @GetMapping("/allergies") fun allergies(@CurrentUser user: AuthenticatedUser): ApiResponse<List<UserAllergy>> = ApiResponse.success(data = healthRecordService.listAllergies(user))
    @PostMapping("/allergies") fun createAllergy(@CurrentUser user: AuthenticatedUser, @RequestBody @Valid request: AllergyRequest): ApiResponse<UserAllergy> = ApiResponse.success(data = healthRecordService.createAllergy(user, request))
    @PatchMapping("/allergies/{id}") fun updateAllergy(@CurrentUser user: AuthenticatedUser, @PathVariable id: Long, @RequestBody @Valid request: AllergyRequest): ApiResponse<UserAllergy> = ApiResponse.success(data = healthRecordService.updateAllergy(user, id, request))
    @DeleteMapping("/allergies/{id}") fun deleteAllergy(@CurrentUser user: AuthenticatedUser, @PathVariable id: Long): ApiResponse<Unit> = delete { healthRecordService.deleteAllergy(user, id) }

    @GetMapping("/medical-conditions") fun conditions(@CurrentUser user: AuthenticatedUser): ApiResponse<List<UserMedicalCondition>> = ApiResponse.success(data = healthRecordService.listMedicalConditions(user))
    @PostMapping("/medical-conditions") fun createCondition(@CurrentUser user: AuthenticatedUser, @RequestBody @Valid request: MedicalConditionRequest): ApiResponse<UserMedicalCondition> = ApiResponse.success(data = healthRecordService.createMedicalCondition(user, request))
    @PatchMapping("/medical-conditions/{id}") fun updateCondition(@CurrentUser user: AuthenticatedUser, @PathVariable id: Long, @RequestBody @Valid request: MedicalConditionRequest): ApiResponse<UserMedicalCondition> = ApiResponse.success(data = healthRecordService.updateMedicalCondition(user, id, request))
    @DeleteMapping("/medical-conditions/{id}") fun deleteCondition(@CurrentUser user: AuthenticatedUser, @PathVariable id: Long): ApiResponse<Unit> = delete { healthRecordService.deleteMedicalCondition(user, id) }

    @GetMapping("/dietary-restrictions") fun restrictions(@CurrentUser user: AuthenticatedUser): ApiResponse<List<UserDietaryRestriction>> = ApiResponse.success(data = healthRecordService.listDietaryRestrictions(user))
    @PostMapping("/dietary-restrictions") fun createRestriction(@CurrentUser user: AuthenticatedUser, @RequestBody @Valid request: DietaryRestrictionRequest): ApiResponse<UserDietaryRestriction> = ApiResponse.success(data = healthRecordService.createDietaryRestriction(user, request))
    @PatchMapping("/dietary-restrictions/{id}") fun updateRestriction(@CurrentUser user: AuthenticatedUser, @PathVariable id: Long, @RequestBody @Valid request: DietaryRestrictionRequest): ApiResponse<UserDietaryRestriction> = ApiResponse.success(data = healthRecordService.updateDietaryRestriction(user, id, request))
    @DeleteMapping("/dietary-restrictions/{id}") fun deleteRestriction(@CurrentUser user: AuthenticatedUser, @PathVariable id: Long): ApiResponse<Unit> = delete { healthRecordService.deleteDietaryRestriction(user, id) }

    @GetMapping("/cuisine-preferences") fun cuisines(@CurrentUser user: AuthenticatedUser): ApiResponse<List<UserCuisinePreference>> = ApiResponse.success(data = healthRecordService.listCuisinePreferences(user))
    @PutMapping("/cuisine-preferences") fun replaceCuisines(@CurrentUser user: AuthenticatedUser, @RequestBody @Valid request: ReplaceCuisinePreferencesRequest): ApiResponse<List<UserCuisinePreference>> = ApiResponse.success(data = healthRecordService.replaceCuisinePreferences(user, request))

    @GetMapping("/clinical-observations") fun observations(@CurrentUser user: AuthenticatedUser): ApiResponse<List<ClinicalObservation>> = ApiResponse.success(data = healthRecordService.listObservations(user))
    @PostMapping("/clinical-observations") fun createObservation(@CurrentUser user: AuthenticatedUser, @RequestBody @Valid request: ClinicalObservationRequest): ApiResponse<ClinicalObservation> = ApiResponse.success(data = healthRecordService.createObservation(user, request))

    @GetMapping("/consents") fun consents(@CurrentUser user: AuthenticatedUser): ApiResponse<List<UserConsent>> = ApiResponse.success(data = healthRecordService.listConsents(user))
    @PostMapping("/consents") fun createConsent(@CurrentUser user: AuthenticatedUser, request: HttpServletRequest, @RequestBody @Valid body: UserConsentRequest): ApiResponse<UserConsent> = ApiResponse.success(data = healthRecordService.createConsent(user, body, request.remoteAddr, request.getHeader("User-Agent")))

    private fun delete(action: () -> Unit): ApiResponse<Unit> {
        action()
        return ApiResponse.success(message = "删除成功")
    }
}
