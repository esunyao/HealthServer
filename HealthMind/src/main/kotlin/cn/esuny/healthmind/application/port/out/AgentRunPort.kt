package cn.esuny.healthmind.application.port.out

import cn.esuny.healthmind.domain.task.AgentRunResult
import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.TaskExecution
import java.util.UUID

interface AgentRunPort {
    /** Launch once for an attempt; an uncertain response must be reconciled instead of retried. */
    fun start(command: TaskExecution): UUID
    /** Read-only reconciliation; never launches a new run. */
    fun reconcile(command: TaskExecution): UUID?
    fun inspect(command: TaskExecution): AgentRunState
    fun cancel(command: TaskExecution)
}

sealed interface AgentRunState {
    data object Active : AgentRunState
    data class Succeeded(val result: AgentRunResult) : AgentRunState
    data class Failed(val code: String, val category: FailureCategory, val summary: String) : AgentRunState
}
