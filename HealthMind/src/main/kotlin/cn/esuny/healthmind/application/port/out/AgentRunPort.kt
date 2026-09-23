package cn.esuny.healthmind.application.port.out

import cn.esuny.healthmind.domain.task.AgentRunResult
import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.TaskExecution
import java.util.UUID

interface AgentRunPort {
    /** The runtime must return the same run for repeated submissions of one attempt. */
    fun start(command: TaskExecution): UUID
    fun inspect(command: TaskExecution): AgentRunState
    fun cancel(command: TaskExecution)
}

sealed interface AgentRunState {
    data object Active : AgentRunState
    data class Succeeded(val result: AgentRunResult) : AgentRunState
    data class Failed(val code: String, val category: FailureCategory, val summary: String) : AgentRunState
}
