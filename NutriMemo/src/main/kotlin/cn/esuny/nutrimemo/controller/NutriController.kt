package cn.esuny.nutrimemo.controller

import cn.esuny.nutrimemo.identity.AuthenticatedUser
import cn.esuny.nutrimemo.identity.CurrentUser
import cn.esuny.nutrimemo.model.*
import cn.esuny.nutrimemo.service.NutriService
import jakarta.validation.Valid
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.time.LocalDate
import java.util.UUID

@RestController
@RequestMapping("/v1/nutri")
class NutriController(private val service: NutriService) {
    @GetMapping("/capture-policy") fun capturePolicy() = ApiResponse.success(service.capturePolicy())

    @PostMapping("/capture-sessions")
    fun createCaptureSession(@CurrentUser user: AuthenticatedUser, @RequestHeader("X-Idempotency-Key") requestId: UUID, @RequestBody @Valid request: CaptureSessionCreateRequest): ResponseEntity<ApiResponse<CaptureSessionView>> {
        val value = service.createCaptureSession(user, requestId, request)
        return ResponseEntity.status(HttpStatus.CREATED).body(ApiResponse.created(value, "创建成功"))
    }
    @GetMapping("/capture-sessions/{sessionId}") fun captureSession(@CurrentUser user: AuthenticatedUser, @PathVariable sessionId: UUID) = ApiResponse.success(service.captureSession(user, sessionId))
    @PostMapping("/capture-sessions/{sessionId}/images/presign") fun presignCaptureImage(@CurrentUser user: AuthenticatedUser, @PathVariable sessionId: UUID, @RequestBody @Valid request: CaptureImagePresignRequest) = ApiResponse.success(service.presignCaptureImage(user, sessionId, request))
    @PostMapping("/capture-sessions/{sessionId}/images/{imageId}/confirm") fun confirmCaptureImage(@CurrentUser user: AuthenticatedUser, @PathVariable sessionId: UUID, @PathVariable imageId: Long) = ApiResponse.success(service.confirmCaptureImage(user, sessionId, imageId))
    @DeleteMapping("/capture-sessions/{sessionId}/images/{imageId}") fun deleteCaptureImage(@CurrentUser user: AuthenticatedUser, @PathVariable sessionId: UUID, @PathVariable imageId: Long): ApiResponse<Unit> { service.deleteCaptureImage(user, sessionId, imageId); return ApiResponse.success(message = "删除成功") }
    @PostMapping("/capture-sessions/{sessionId}/submit") @ResponseStatus(HttpStatus.ACCEPTED) fun submitCapture(@CurrentUser user: AuthenticatedUser, @PathVariable sessionId: UUID) = ApiResponse.success(service.submitCapture(user, sessionId), "已提交识别")
    @PostMapping("/capture-sessions/{sessionId}/retry") @ResponseStatus(HttpStatus.ACCEPTED) fun retryCapture(@CurrentUser user: AuthenticatedUser, @PathVariable sessionId: UUID) = ApiResponse.success(service.retryCapture(user, sessionId), "已重新提交识别")
    @DeleteMapping("/capture-sessions/{sessionId}") fun cancelCapture(@CurrentUser user: AuthenticatedUser, @PathVariable sessionId: UUID): ApiResponse<Unit> { service.cancelCapture(user, sessionId); return ApiResponse.success(message = "已取消") }

    @GetMapping("/meals") fun meals(@CurrentUser user: AuthenticatedUser, @RequestParam dateFrom: LocalDate, @RequestParam dateTo: LocalDate, @RequestParam(required = false) mealType: String?, @RequestParam(required = false) q: String?, @RequestParam(defaultValue = "1") page: Int, @RequestParam(defaultValue = "20") pageSize: Int) = ApiResponse.success(service.meals(user, dateFrom, dateTo, mealType, q, page, pageSize))
    @GetMapping("/meals/{mealId}") fun meal(@CurrentUser user: AuthenticatedUser, @PathVariable mealId: Long) = ApiResponse.success(service.meal(user, mealId))
    @PutMapping("/meals/{mealId}") fun replaceMeal(@CurrentUser user: AuthenticatedUser, @PathVariable mealId: Long, @RequestBody @Valid request: MealCorrectionRequest) = ApiResponse.success(service.replaceMeal(user, mealId, request))
    @DeleteMapping("/meals/{mealId}") fun deleteMeal(@CurrentUser user: AuthenticatedUser, @PathVariable mealId: Long): ApiResponse<Unit> { service.deleteMeal(user, mealId); return ApiResponse.success(message = "删除成功") }
    @GetMapping("/summaries/daily") fun daily(@CurrentUser user: AuthenticatedUser, @RequestParam localDate: LocalDate) = ApiResponse.success(service.dailySummary(user, localDate))
    @GetMapping("/summaries/daily-trend") fun dailyTrend(@CurrentUser user: AuthenticatedUser, @RequestParam dateFrom: LocalDate, @RequestParam dateTo: LocalDate) = ApiResponse.success(service.dailyTrend(user, dateFrom, dateTo))
}
