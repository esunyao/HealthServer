package cn.esuny.nutrimemo.controller

import cn.esuny.nutrimemo.identity.AuthenticatedUser
import cn.esuny.nutrimemo.identity.CurrentUser
import cn.esuny.nutrimemo.model.ApiResponse
import cn.esuny.nutrimemo.model.CustomFoodRequest
import cn.esuny.nutrimemo.model.MealImageConfirmRequest
import cn.esuny.nutrimemo.model.MealImagePresignRequest
import cn.esuny.nutrimemo.model.MealUpsertRequest
import cn.esuny.nutrimemo.service.NutriService
import jakarta.validation.Valid
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.DeleteMapping
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PatchMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestHeader
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestController
import java.time.LocalDate
import java.util.UUID

@RestController
@RequestMapping("/v1/nutri")
class NutriController(private val service: NutriService) {
    @GetMapping("/foods")
    fun foods(@CurrentUser user: AuthenticatedUser, @RequestParam(required = false) q: String?, @RequestParam(required = false) foodType: String?, @RequestParam(defaultValue = "true") includeCustom: Boolean, @RequestParam(defaultValue = "1") page: Int, @RequestParam(defaultValue = "20") pageSize: Int) = ApiResponse.success(service.searchFoods(user, q, foodType, includeCustom, page, pageSize))

    @GetMapping("/foods/{foodId}") fun food(@CurrentUser user: AuthenticatedUser, @PathVariable foodId: Long) = ApiResponse.success(service.food(user, foodId))
    @GetMapping("/custom-foods") fun customFoods(@CurrentUser user: AuthenticatedUser, @RequestParam(defaultValue = "false") includeInactive: Boolean, @RequestParam(defaultValue = "1") page: Int, @RequestParam(defaultValue = "20") pageSize: Int) = ApiResponse.success(service.customFoods(user, includeInactive, page, pageSize))

    @PostMapping("/custom-foods") @ResponseStatus(HttpStatus.CREATED)
    fun createCustomFood(@CurrentUser user: AuthenticatedUser, @RequestBody @Valid request: CustomFoodRequest) = ApiResponse.created(service.createCustomFood(user, request), "创建成功")
    @PatchMapping("/custom-foods/{foodId}") fun updateCustomFood(@CurrentUser user: AuthenticatedUser, @PathVariable foodId: Long, @RequestBody @Valid request: CustomFoodRequest) = ApiResponse.success(service.updateCustomFood(user, foodId, request))
    @DeleteMapping("/custom-foods/{foodId}") fun deleteCustomFood(@CurrentUser user: AuthenticatedUser, @PathVariable foodId: Long): ApiResponse<Unit> { service.deactivateCustomFood(user, foodId); return ApiResponse.success(message = "删除成功") }

    @GetMapping("/meals")
    fun meals(@CurrentUser user: AuthenticatedUser, @RequestParam dateFrom: LocalDate, @RequestParam dateTo: LocalDate, @RequestParam(required = false) mealType: String?, @RequestParam(defaultValue = "1") page: Int, @RequestParam(defaultValue = "20") pageSize: Int) = ApiResponse.success(service.meals(user, dateFrom, dateTo, mealType, page, pageSize))
    @GetMapping("/meals/{mealId}") fun meal(@CurrentUser user: AuthenticatedUser, @PathVariable mealId: Long) = ApiResponse.success(service.meal(user, mealId))
    @PostMapping("/meals") @ResponseStatus(HttpStatus.CREATED)
    fun createMeal(@CurrentUser user: AuthenticatedUser, @RequestHeader("X-Idempotency-Key") idempotencyKey: UUID, @RequestBody @Valid request: MealUpsertRequest) = ApiResponse.created(service.createMeal(user, idempotencyKey, request), "创建成功")
    @PutMapping("/meals/{mealId}") fun replaceMeal(@CurrentUser user: AuthenticatedUser, @PathVariable mealId: Long, @RequestBody @Valid request: MealUpsertRequest) = ApiResponse.success(service.replaceMeal(user, mealId, request))
    @DeleteMapping("/meals/{mealId}") fun deleteMeal(@CurrentUser user: AuthenticatedUser, @PathVariable mealId: Long): ApiResponse<Unit> { service.deleteMeal(user, mealId); return ApiResponse.success(message = "删除成功") }

    @PostMapping("/meals/{mealId}/images/presign")
    fun presignImage(@CurrentUser user: AuthenticatedUser, @PathVariable mealId: Long, @RequestBody @Valid request: MealImagePresignRequest) = ApiResponse.success(service.presignImage(user, mealId, request))
    @PostMapping("/meals/{mealId}/images/confirm") @ResponseStatus(HttpStatus.CREATED)
    fun confirmImage(@CurrentUser user: AuthenticatedUser, @PathVariable mealId: Long, @RequestBody @Valid request: MealImageConfirmRequest) = ApiResponse.created(service.confirmImage(user, mealId, request), "确认成功")
    @DeleteMapping("/meals/{mealId}/images/{imageId}") fun deleteImage(@CurrentUser user: AuthenticatedUser, @PathVariable mealId: Long, @PathVariable imageId: Long): ApiResponse<Unit> { service.deleteImage(user, mealId, imageId); return ApiResponse.success(message = "删除成功") }

    @GetMapping("/summaries/daily") fun daily(@CurrentUser user: AuthenticatedUser, @RequestParam localDate: LocalDate) = ApiResponse.success(service.dailySummary(user, localDate))
    @GetMapping("/summaries/daily-trend") fun dailyTrend(@CurrentUser user: AuthenticatedUser, @RequestParam dateFrom: LocalDate, @RequestParam dateTo: LocalDate) = ApiResponse.success(service.dailyTrend(user, dateFrom, dateTo))
}
