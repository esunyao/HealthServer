package cn.esuny.healthmind.application.port.out

import cn.esuny.healthmind.infrastructure.database.ToolInvocationRepository
import tools.jackson.databind.JsonNode

interface InternalContextPort {
    fun getNutritionContext(grant: ToolInvocationRepository.ToolGrant): JsonNode
    fun getCaptureContext(grant: ToolInvocationRepository.ToolGrant): JsonNode
}
