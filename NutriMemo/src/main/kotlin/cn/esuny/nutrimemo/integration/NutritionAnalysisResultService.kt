package cn.esuny.nutrimemo.integration

import cn.esuny.contracts.integration.v1.NutritionEventTypes
import cn.esuny.nutrimemo.model.MealItemRecord
import cn.esuny.nutrimemo.persistence.NutriRepository
import cn.esuny.nutrimemo.service.SnowflakeIdGenerator
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import tools.jackson.databind.JsonNode
import java.math.BigDecimal
import java.util.UUID

@Service
class NutritionAnalysisResultService(
    private val resultRepository: NutritionResultRepository,
    private val nutriRepository: NutriRepository,
    private val ids: SnowflakeIdGenerator,
    private val json: CanonicalEventJson,
) {
    @Transactional
    fun process(raw: String) {
        val root = json.parse(raw)
        val eventId = UUID.fromString(requiredText(root, "event_id"))
        val eventType = requiredText(root, "event_type")
        if (!resultRepository.startInbox(eventId, eventType, json.digest(root))) return
        try {
            require(requiredText(root, "schema_version") == NutritionEventTypes.SCHEMA_VERSION) { "UNSUPPORTED_SCHEMA_VERSION" }
            require(eventType in setOf(NutritionEventTypes.ANALYSIS_COMPLETED, NutritionEventTypes.ANALYSIS_FAILED)) { "UNSUPPORTED_EVENT_TYPE" }
            require(requiredText(root, "producer") == "HealthMind") { "UNTRUSTED_EVENT_PRODUCER" }
            val subjectId = UUID.fromString(requiredText(root, "subject_id"))
            val payload = root.path("payload")
            val captureSessionId = UUID.fromString(requiredText(payload, "capture_session_id"))
            val mealId = payload.path("meal_id").asLong()
            require(mealId > 0) { "INVALID_MEAL_ID" }
            val meal = resultRepository.lockMeal(captureSessionId, mealId)
            if (meal == null) {
                resultRepository.completeInbox(eventId)
                return
            }
            require(meal.userId == subjectId) { "EVENT_SUBJECT_MISMATCH" }
            if (eventType == NutritionEventTypes.ANALYSIS_COMPLETED) applyCompleted(meal, payload)
            else applyFailed(meal)
            resultRepository.completeInbox(eventId)
        } catch (exception: IllegalArgumentException) {
            resultRepository.failInbox(eventId, exception.message ?: "INVALID_EVENT")
        }
    }

    private fun applyCompleted(meal: NutritionResultRepository.ResultMeal, payload: JsonNode) {
        val manual = resultRepository.hasManualOrCorrectedItems(meal.mealId)
        when (AiWritebackPolicy.decide(meal.status, manual)) {
            AiWritebackDecision.IGNORE_DELETED -> return
            AiWritebackDecision.PRESERVE_MANUAL -> {
                resultRepository.markCompleted(meal, updateMeal = false)
                return
            }
            AiWritebackDecision.APPLY_AI -> Unit
        }
        val inputs = payload.path("items").values().mapIndexed { index, node -> parseItem(index, node) }
        require(inputs.isNotEmpty() && inputs.size <= 100) { "INVALID_AI_ITEMS" }
        val codes = inputs.flatMap { it.nutrients }.map { it.first }.toSet()
        val definitions = nutriRepository.nutrientsByCodes(codes).associateBy { it.nutrientCode }
        require(definitions.size == codes.size && definitions.values.all { it.active }) { "UNKNOWN_NUTRIENT_CODE" }
        val items = inputs.mapIndexed { index, input ->
            MealItemRecord(ids.nextId(), meal.mealId, index + 1, input.name, input.weight, input.confidence, "ai", false, null)
        }
        val values = items.zip(inputs).associate { (item, input) ->
            item.itemId to input.nutrients.map { (code, value) -> definitions.getValue(code) to value }
        }
        nutriRepository.replaceAiItems(meal.mealId, items, values)
        resultRepository.markCompleted(meal, updateMeal = true)
        nutriRepository.recalculateDaily(meal.userId, meal.localDate, ids.nextId())
    }

    private fun applyFailed(meal: NutritionResultRepository.ResultMeal) {
        val manual = resultRepository.hasManualOrCorrectedItems(meal.mealId)
        if (meal.status == "deleted") return
        if (manual || meal.analysisStatus == "completed") resultRepository.markCompleted(meal, updateMeal = false)
        else resultRepository.markFailed(meal)
    }

    private fun parseItem(index: Int, node: JsonNode): AiItem {
        val name = requiredText(node, "name").trim()
        require(name.isNotEmpty() && name.length <= 150) { "INVALID_ITEM_NAME_$index" }
        val weight = node.path("weight_grams").decimalValue()
        val confidence = node.path("confidence").decimalValue()
        require(weight > BigDecimal.ZERO && confidence >= BigDecimal.ZERO && confidence <= BigDecimal.ONE) { "INVALID_ITEM_VALUE_$index" }
        val nutrients = node.path("nutrients").values().map { nutrient ->
            val code = requiredText(nutrient, "code").trim().uppercase()
            val value = nutrient.path("value").decimalValue()
            require(code.matches(Regex("^[A-Z0-9_]{1,32}$")) && value >= BigDecimal.ZERO) { "INVALID_NUTRIENT_$index" }
            code to value
        }
        require(nutrients.isNotEmpty() && nutrients.map { it.first }.toSet().size == nutrients.size) { "INVALID_NUTRIENTS_$index" }
        return AiItem(name, weight, confidence, nutrients)
    }

    private fun requiredText(node: JsonNode, field: String): String = node.path(field).asString().takeIf { it.isNotBlank() }
        ?: throw IllegalArgumentException("MISSING_$field")

    private data class AiItem(
        val name: String,
        val weight: BigDecimal,
        val confidence: BigDecimal,
        val nutrients: List<Pair<String, BigDecimal>>,
    )
}
