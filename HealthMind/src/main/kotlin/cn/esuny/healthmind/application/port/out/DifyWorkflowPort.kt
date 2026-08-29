package cn.esuny.healthmind.application.port.out

import cn.esuny.healthmind.domain.task.DifyWorkflowResult
import cn.esuny.healthmind.domain.task.TaskExecution

fun interface DifyWorkflowPort {
    fun run(command: TaskExecution): DifyWorkflowResult
}
