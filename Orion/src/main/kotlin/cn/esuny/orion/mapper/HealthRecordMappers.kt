package cn.esuny.orion.mapper

import cn.esuny.orion.model.entity.user.ClinicalObservation
import cn.esuny.orion.model.entity.user.UserAllergy
import cn.esuny.orion.model.entity.user.UserBodyMeasurement
import cn.esuny.orion.model.entity.user.UserConsent
import cn.esuny.orion.model.entity.user.UserCuisinePreference
import cn.esuny.orion.model.entity.user.UserDietaryRestriction
import cn.esuny.orion.model.entity.user.UserHealthGoal
import cn.esuny.orion.model.entity.user.UserMedicalCondition
import com.baomidou.mybatisplus.core.mapper.BaseMapper
import org.apache.ibatis.annotations.Mapper

@Mapper interface UserBodyMeasurementMapper : BaseMapper<UserBodyMeasurement>
@Mapper interface UserHealthGoalMapper : BaseMapper<UserHealthGoal>
@Mapper interface UserAllergyMapper : BaseMapper<UserAllergy>
@Mapper interface UserMedicalConditionMapper : BaseMapper<UserMedicalCondition>
@Mapper interface UserDietaryRestrictionMapper : BaseMapper<UserDietaryRestriction>
@Mapper interface UserCuisinePreferenceMapper : BaseMapper<UserCuisinePreference>
@Mapper interface ClinicalObservationMapper : BaseMapper<ClinicalObservation>
@Mapper interface UserConsentMapper : BaseMapper<UserConsent>
