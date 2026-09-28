package cn.esuny.healthmind.application.port.out

import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.TaskExecution
import tools.jackson.databind.JsonNode
import java.util.UUID

/** Translates a task result into the integration event owned by that task type. */
interface TaskOutcomePort {
    fun completedEvent(command: TaskExecution, result: JsonNode): TaskOutboxMessage

    fun failedEvent(command: TaskExecution, category: FailureCategory, code: String, message: String): TaskOutboxMessage
}

data class TaskOutboxMessage(
    val eventId: UUID,
    val eventType: String,
    val schemaVersion: String,
    val destinationKey: String,
    val partitionKey: String,
    val payload: JsonNode,
)
