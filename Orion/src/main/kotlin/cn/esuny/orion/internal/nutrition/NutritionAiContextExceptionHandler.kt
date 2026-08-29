package cn.esuny.orion.internal.nutrition

import org.springframework.core.Ordered
import org.springframework.core.annotation.Order
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.RestControllerAdvice

@Order(Ordered.HIGHEST_PRECEDENCE)
@RestControllerAdvice(assignableTypes = [NutritionAiContextController::class])
class NutritionAiContextExceptionHandler {
    @ExceptionHandler(AiNutritionConsentRequiredException::class)
    fun consentRequired(): ResponseEntity<Map<String, Any>> = ResponseEntity.status(HttpStatus.FORBIDDEN).body(
        mapOf("error_code" to "AI_CONTEXT_CONSENT_REQUIRED", "message" to "AI nutrition analysis consent is required"),
    )
}
