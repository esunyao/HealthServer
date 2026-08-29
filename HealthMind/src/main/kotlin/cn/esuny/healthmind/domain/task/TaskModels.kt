package cn.esuny.healthmind.domain.task

import java.util.UUID

enum class FailureCategory(val wireValue: String, val retryable: Boolean) {
    TRANSIENT("transient", true),
    PERMANENT("permanent", false),
    CONTRACT("contract", false),
    TIMEOUT("timeout", true),
    CANCELLED("cancelled", false),
}

data class TaskExecution(
    val taskId: UUID,
    val attemptId: UUID,
    val attemptNo: Int,
    val maxAttempts: Int,
    val lockVersion: Long,
    val subjectId: UUID?,
    val aggregateType: String,
    val aggregateId: String,
    val captureSessionId: UUID,
    val mealId: Long,
    val traceId: String,
    val difyAppId: String,
    val difyWorkflowId: String,
    val difyWorkflowVersion: String,
    val outputSchemaVersion: String,
    val outputSchema: String,
    val timeoutSeconds: Int,
)

data class DifyWorkflowResult(
    val workflowRunId: String,
    val workflowId: String,
    val outputJson: String,
    val providerName: String? = null,
    val modelName: String? = null,
    val modelVersion: String? = null,
    val inputTokens: Long? = null,
    val outputTokens: Long? = null,
)

class TaskExecutionException(
    val code: String,
    val category: FailureCategory,
    message: String,
    cause: Throwable? = null,
) : RuntimeException(message, cause)
