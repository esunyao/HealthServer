package cn.esuny.contracts.integration.v1

import com.fasterxml.jackson.annotation.JsonProperty
import java.math.BigDecimal
import java.time.Instant
import java.util.UUID

object NutritionEventTypes {
    const val CAPTURE_READY = "nutrition.capture.ready.v1"
    const val ANALYSIS_COMPLETED = "nutrition.analysis.completed.v1"
    const val ANALYSIS_FAILED = "nutrition.analysis.failed.v1"
    const val SCHEMA_VERSION = "1.0"
}

data class IntegrationEvent<T>(
    @JsonProperty("event_id") val eventId: UUID,
    @JsonProperty("event_type") val eventType: String,
    @JsonProperty("occurred_at") val occurredAt: Instant,
    val producer: String,
    @JsonProperty("trace_id") val traceId: String,
    @JsonProperty("subject_id") val subjectId: UUID,
    @JsonProperty("aggregate_type") val aggregateType: String,
    @JsonProperty("aggregate_id") val aggregateId: String,
    @JsonProperty("schema_version") val schemaVersion: String = NutritionEventTypes.SCHEMA_VERSION,
    val payload: T,
)

data class NutritionCaptureReadyPayload(
    @JsonProperty("capture_session_id") val captureSessionId: Long,
    @JsonProperty("meal_id") val mealId: Long,
)

data class NutritionAnalysisCompletedPayload(
    @JsonProperty("task_id") val taskId: UUID,
    @JsonProperty("capture_session_id") val captureSessionId: Long,
    @JsonProperty("meal_id") val mealId: Long,
    @JsonProperty("result_version") val resultVersion: Int,
    @JsonProperty("overall_confidence") val overallConfidence: BigDecimal,
    val items: List<AnalyzedMealItem>,
)

data class AnalyzedMealItem(
    val name: String,
    @JsonProperty("weight_grams") val weightGrams: BigDecimal,
    val confidence: BigDecimal,
    val nutrients: List<AnalyzedNutrient>,
)

data class AnalyzedNutrient(
    val code: String,
    val value: BigDecimal,
)

data class NutritionAnalysisFailedPayload(
    @JsonProperty("task_id") val taskId: UUID,
    @JsonProperty("capture_session_id") val captureSessionId: Long,
    @JsonProperty("meal_id") val mealId: Long,
    @JsonProperty("error_code") val errorCode: String,
    @JsonProperty("failure_category") val failureCategory: String,
    val retryable: Boolean,
    @JsonProperty("error_summary") val errorSummary: String,
)
