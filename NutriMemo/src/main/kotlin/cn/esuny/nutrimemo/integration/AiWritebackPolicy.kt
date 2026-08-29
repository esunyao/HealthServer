package cn.esuny.nutrimemo.integration

enum class AiWritebackDecision { IGNORE_DELETED, PRESERVE_MANUAL, APPLY_AI }

object AiWritebackPolicy {
    fun decide(mealStatus: String, hasManualOrCorrectedItems: Boolean): AiWritebackDecision = when {
        mealStatus == "deleted" -> AiWritebackDecision.IGNORE_DELETED
        hasManualOrCorrectedItems -> AiWritebackDecision.PRESERVE_MANUAL
        else -> AiWritebackDecision.APPLY_AI
    }
}
