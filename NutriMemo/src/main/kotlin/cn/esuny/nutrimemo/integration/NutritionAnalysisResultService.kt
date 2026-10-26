package cn.esuny.nutrimemo.integration

import cn.esuny.contracts.integration.v1.NutritionEventTypes
import cn.esuny.nutrimemo.model.MealAnalysisReportRecord
import cn.esuny.nutrimemo.model.MealItemRecord
import cn.esuny.nutrimemo.persistence.NutriRepository
import cn.esuny.nutrimemo.service.SnowflakeIdGenerator
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import tools.jackson.databind.JsonNode
import java.math.BigDecimal
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeParseException
import java.util.UUID

@Service
class NutritionAnalysisResultService(
    private val resultRepository: NutritionResultRepository,
    private val nutriRepository: NutriRepository,
    private val ids: SnowflakeIdGenerator,
    private val json: CanonicalEventJson,
) {
    @Transactional(noRollbackFor = [UnrecoverableResultEventException::class])
    fun process(raw: String) {
        var eventId: UUID? = null
        var eventType: String? = null
        var meal: NutritionResultRepository.ResultMeal? = null
        var taskId = UNKNOWN_TASK_ID
        var occurredAt = UNKNOWN_OCCURRED_AT
        var inboxStarted = false
        var payloadDigest = digestRaw(raw)
        var root: JsonNode? = null
        try {
            val parsedRoot = try {
                json.parse(raw)
            } catch (exception: Exception) {
                throw UnrecoverableResultEventException("UNPARSEABLE_EVENT", "Result event is not valid JSON", exception)
            }
            root = parsedRoot
            payloadDigest = json.digest(parsedRoot)
            eventType = parsedRoot.path("event_type").asString().trim()
                .takeIf { it.isNotBlank() && it != "null" }
                ?.take(100)
            val acceptedEventId = parseUuid(parsedRoot, "event_id", "INVALID_EVENT_ID")
            eventId = acceptedEventId
            if (!resultRepository.startInbox(acceptedEventId, eventType ?: UNKNOWN_EVENT_TYPE, payloadDigest)) return
            inboxStarted = true

            val payload = parsedRoot.path("payload")
            val captureSessionId = parseUuid(payload, "capture_session_id", "INVALID_CAPTURE_SESSION_ID")
            val mealId = payload.path("meal_id").asLong()
            if (mealId <= 0) {
                throw UnrecoverableResultEventException("INVALID_MEAL_ID", "Result event has an invalid meal_id")
            }
            val lockedMeal = resultRepository.lockMeal(captureSessionId, mealId)
                ?: throw UnrecoverableResultEventException("MEAL_NOT_FOUND", "Result event does not match a locked meal")
            meal = lockedMeal
            taskId = parseUuid(payload, "task_id", "INVALID_TASK_ID")
            occurredAt = parseOccurredAt(parsedRoot)

            require(requiredText(parsedRoot, "schema_version") == NutritionEventTypes.SCHEMA_VERSION) { "UNSUPPORTED_SCHEMA_VERSION" }
            require(
                eventType in setOf(
                    NutritionEventTypes.ANALYSIS_COMPLETED,
                    NutritionEventTypes.ANALYSIS_FAILED,
                    NutritionEventTypes.ANALYSIS_REVIEW_REQUIRED,
                ),
            ) { "UNSUPPORTED_EVENT_TYPE" }
            require(requiredText(parsedRoot, "producer") == "HealthMind") { "UNTRUSTED_EVENT_PRODUCER" }
            require(parsedRoot.path("aggregate_type").asString() == "meal") { "INVALID_AGGREGATE_TYPE" }
            require(parsedRoot.path("aggregate_id").asString() == lockedMeal.mealId.toString()) { "INVALID_MEAL_ID" }
            val subjectId = parseUuid(parsedRoot, "subject_id", "INVALID_SUBJECT_ID")
            require(lockedMeal.userId == subjectId) { "EVENT_SUBJECT_MISMATCH" }
            val applied = when (eventType) {
                NutritionEventTypes.ANALYSIS_COMPLETED -> applyCompleted(lockedMeal, acceptedEventId, taskId, occurredAt, payload)
                NutritionEventTypes.ANALYSIS_FAILED -> applyFailed(lockedMeal, acceptedEventId, taskId, occurredAt, payload)
                else -> applyReviewRequired(lockedMeal, acceptedEventId, taskId, occurredAt, payload)
            }
            if (!applied) {
                resultRepository.completeInbox(acceptedEventId)
                return
            }
            resultRepository.completeInbox(acceptedEventId)
        } catch (exception: UnrecoverableResultEventException) {
            recoverMealForRejection(root, eventId, meal)?.let {
                meal = it.meal
                taskId = it.taskId
                occurredAt = it.occurredAt
            }
            reject(
                raw = raw,
                eventId = eventId,
                eventType = eventType,
                meal = meal,
                taskId = taskId,
                occurredAt = occurredAt,
                payloadDigest = payloadDigest,
                inboxStarted = inboxStarted,
                reasonCode = exception.reasonCode,
                message = exception.message ?: exception.reasonCode,
            )
            throw exception
        } catch (exception: IllegalArgumentException) {
            val reason = exception.message ?: "INVALID_EVENT"
            val rejected = UnrecoverableResultEventException("EVENT_CONTRACT_INVALID", reason, exception)
            recoverMealForRejection(root, eventId, meal)?.let {
                meal = it.meal
                taskId = it.taskId
                occurredAt = it.occurredAt
            }
            reject(
                raw = raw,
                eventId = eventId,
                eventType = eventType,
                meal = meal,
                taskId = taskId,
                occurredAt = occurredAt,
                payloadDigest = payloadDigest,
                inboxStarted = inboxStarted,
                reasonCode = rejected.reasonCode,
                message = reason,
            )
            throw rejected
        }
    }

    private fun reject(
        raw: String,
        eventId: UUID?,
        eventType: String?,
        meal: NutritionResultRepository.ResultMeal?,
        taskId: UUID,
        occurredAt: OffsetDateTime,
        payloadDigest: String,
        inboxStarted: Boolean,
        reasonCode: String,
        message: String,
    ) {
        val normalizedCode = reasonCode.takeIf { it.matches(FAILURE_CODE) } ?: "RESULT_EVENT_REJECTED"
        val normalizedMessage = message.ifBlank { normalizedCode }.take(1000)
        if (meal != null) {
            applyInvalidResult(
                meal = meal,
                sourceEventId = eventId ?: syntheticEventId(payloadDigest),
                taskId = taskId,
                occurredAt = occurredAt,
                reasonCode = normalizedCode,
                message = normalizedMessage,
            )
        }
        if (inboxStarted && eventId != null) resultRepository.failInbox(eventId, normalizedMessage)
        resultRepository.recordDeadLetter(
            eventId = eventId,
            eventType = eventType,
            mealId = meal?.mealId,
            payloadDigest = payloadDigest,
            rawPayload = raw.replace("\u0000", "\\u0000").take(MAX_RAW_PAYLOAD_CHARS),
            failureCode = normalizedCode,
            failureMessage = normalizedMessage,
        )
    }

    private fun applyCompleted(
        meal: NutritionResultRepository.ResultMeal,
        eventId: UUID,
        taskId: UUID,
        occurredAt: OffsetDateTime,
        payload: JsonNode,
    ): Boolean {
        val resultVersion = positiveInt(payload, "result_version")
        val confidence = unitDecimal(payload, "overall_confidence")
        val inputs = parseItems(payload)
        val codes = inputs.flatMap { it.nutrients }.map { it.first }.toSet()
        val definitions = nutriRepository.nutrientsByCodes(codes).associateBy { it.nutrientCode }
        require(definitions.size == codes.size && definitions.values.all { it.active }) { "UNKNOWN_NUTRIENT_CODE" }
        val reportAccepted = resultRepository.saveReport(
            MealAnalysisReportRecord(
                meal.mealId, taskId, eventId, occurredAt, "completed", confidence, resultVersion, null, null, occurredAt,
            ),
        )
        if (!reportAccepted) return false
        val manual = resultRepository.hasManualOrCorrectedItems(meal.mealId)
        when (AiWritebackPolicy.decide(meal.status, manual)) {
            AiWritebackDecision.IGNORE_DELETED -> return true
            AiWritebackDecision.PRESERVE_MANUAL -> {
                resultRepository.markCompleted(meal, updateMeal = true)
                return true
            }
            AiWritebackDecision.APPLY_AI -> Unit
        }
        val items = inputs.mapIndexed { index, input ->
            MealItemRecord(ids.nextId(), meal.mealId, index + 1, input.name, input.weight, input.confidence, "ai", false, null)
        }
        val values = items.zip(inputs).associate { (item, input) ->
            item.itemId to input.nutrients.map { (code, value) -> definitions.getValue(code) to value }
        }
        nutriRepository.replaceAiItems(meal.mealId, items, values)
        resultRepository.markCompleted(meal, updateMeal = true)
        nutriRepository.recalculateDaily(meal.userId, meal.localDate, ids.nextId())
        return true
    }

    private fun applyFailed(
        meal: NutritionResultRepository.ResultMeal,
        eventId: UUID,
        taskId: UUID,
        occurredAt: OffsetDateTime,
        payload: JsonNode,
    ): Boolean {
        val reasonCode = reasonCode(payload, "error_code")
        val message = message(payload, "error_summary")
        val category = requiredText(payload, "failure_category")
        require(category in FAILURE_CATEGORIES) { "INVALID_FAILURE_CATEGORY" }
        val retryable = payload.path("retryable")
        require(retryable.isBoolean && retryable.booleanValue() == (category in RETRYABLE_CATEGORIES)) {
            "INVALID_RETRYABLE"
        }
        return applyTerminal(
            meal, eventId, taskId, occurredAt, "failed", reasonCode, message, resultRepository::markFailed,
        )
    }

    private fun applyReviewRequired(
        meal: NutritionResultRepository.ResultMeal,
        eventId: UUID,
        taskId: UUID,
        occurredAt: OffsetDateTime,
        payload: JsonNode,
    ): Boolean {
        val reasonCode = reasonCode(payload, "reason_code")
        val message = message(payload, "message")
        val retryable = payload.path("retryable")
        require(retryable.isBoolean && !retryable.booleanValue()) { "INVALID_RETRYABLE" }
        return applyTerminal(
            meal, eventId, taskId, occurredAt, "needs_review", reasonCode, message, resultRepository::markNeedsReview,
        )
    }

    private fun applyTerminal(
        meal: NutritionResultRepository.ResultMeal,
        eventId: UUID,
        taskId: UUID,
        occurredAt: OffsetDateTime,
        status: String,
        reasonCode: String,
        message: String,
        markTerminal: (NutritionResultRepository.ResultMeal) -> Unit,
    ): Boolean {
        val reportAccepted = resultRepository.saveReport(
            MealAnalysisReportRecord(
                meal.mealId, taskId, eventId, occurredAt, status, null, null, reasonCode, message, occurredAt,
            ),
        )
        if (!reportAccepted) return false
        val manual = resultRepository.hasManualOrCorrectedItems(meal.mealId)
        if (meal.status == "deleted") return true
        if (manual || meal.analysisStatus == "completed") resultRepository.markCompleted(meal, updateMeal = true)
        else markTerminal(meal)
        return true
    }

    private fun applyInvalidResult(
        meal: NutritionResultRepository.ResultMeal,
        sourceEventId: UUID,
        taskId: UUID,
        occurredAt: OffsetDateTime,
        reasonCode: String,
        message: String,
    ) {
        val accepted = resultRepository.saveReport(
            MealAnalysisReportRecord(
                meal.mealId, taskId, sourceEventId, occurredAt, "failed", null, null, reasonCode,
                message.take(500), OffsetDateTime.now(ZoneOffset.UTC),
            ),
        )
        if (!accepted) return
        if (meal.status == "deleted") return
        if (resultRepository.hasManualOrCorrectedItems(meal.mealId)) {
            resultRepository.markCompleted(meal, updateMeal = true)
        } else {
            resultRepository.markFailed(meal)
        }
    }

    private fun parseItems(payload: JsonNode): List<AiItem> {
        val inputs = payload.path("items").values().mapIndexed { index, node -> parseItem(index, node) }
        require(inputs.isNotEmpty() && inputs.size <= 100) { "INVALID_AI_ITEMS" }
        return inputs
    }

    private fun parseItem(index: Int, node: JsonNode): AiItem {
        val name = requiredText(node, "name").trim()
        require(name.isNotEmpty() && name.length <= 150) { "INVALID_ITEM_NAME_$index" }
        val weight = decimal(node, "weight_grams").takeIf { it > BigDecimal.ZERO } ?: throw IllegalArgumentException("INVALID_ITEM_VALUE_$index")
        val confidence = unitDecimal(node, "confidence")
        require(weight > BigDecimal.ZERO && confidence >= BigDecimal.ZERO && confidence <= BigDecimal.ONE) { "INVALID_ITEM_VALUE_$index" }
        val nutrients = node.path("nutrients").values().map { nutrient ->
            val code = requiredText(nutrient, "code").trim().uppercase()
            val value = decimal(nutrient, "value").takeIf { it >= BigDecimal.ZERO }
                ?: throw IllegalArgumentException("INVALID_NUTRIENT_$index")
            require(code.matches(Regex("^[A-Z0-9_]{1,32}$"))) { "INVALID_NUTRIENT_$index" }
            code to value
        }
        require(nutrients.isNotEmpty() && nutrients.map { it.first }.toSet().size == nutrients.size) { "INVALID_NUTRIENTS_$index" }
        return AiItem(name, weight, confidence, nutrients)
    }

    private fun positiveInt(node: JsonNode, field: String): Int {
        val value = node.path(field)
        require(value.isIntegralNumber && value.intValue() > 0) { "INVALID_$field" }
        return value.intValue()
    }

    private fun unitDecimal(node: JsonNode, field: String): BigDecimal {
        val value = decimal(node, field)
        require(value >= BigDecimal.ZERO && value <= BigDecimal.ONE) { "INVALID_$field" }
        return value
    }

    private fun decimal(node: JsonNode, field: String): BigDecimal {
        val value = node.path(field)
        require(value.isNumber) { "INVALID_$field" }
        return value.decimalValue()
    }

    private fun reasonCode(payload: JsonNode, field: String): String = requiredText(payload, field)
        .trim()
        .takeIf { it.matches(Regex("^[A-Z0-9_]{1,64}$")) }
        ?: throw IllegalArgumentException("INVALID_$field")

    private fun message(payload: JsonNode, field: String): String = requiredText(payload, field)
        .trim()
        .takeIf { it.length in 1..500 }
        ?: throw IllegalArgumentException("INVALID_$field")

    private fun requiredText(node: JsonNode, field: String): String = node.path(field).asString().takeIf { it.isNotBlank() }
        ?: throw IllegalArgumentException("MISSING_$field")

    private fun parseUuid(node: JsonNode, field: String, reason: String): UUID {
        val raw = node.path(field).asString()
        return runCatching { UUID.fromString(raw) }.getOrElse { error ->
            throw UnrecoverableResultEventException(reason, reason, error)
        }
    }

    private fun parseOccurredAt(root: JsonNode): OffsetDateTime = try {
        OffsetDateTime.parse(requiredText(root, "occurred_at"))
    } catch (exception: DateTimeParseException) {
        throw UnrecoverableResultEventException("INVALID_OCCURRED_AT", "Result event has an invalid occurred_at", exception)
    }

    private fun recoverMealForRejection(
        root: JsonNode?,
        eventId: UUID?,
        currentMeal: NutritionResultRepository.ResultMeal?,
    ): RejectedMealContext? {
        if (root == null || eventId != null || currentMeal != null) return null
        return runCatching {
            val payload = root.path("payload")
            val captureSessionId = UUID.fromString(payload.path("capture_session_id").asString())
            val mealId = payload.path("meal_id").asLong()
            if (mealId <= 0) return null
            val meal = resultRepository.lockMeal(captureSessionId, mealId) ?: return null
            val taskId = runCatching {
                UUID.fromString(payload.path("task_id").asString())
            }.getOrDefault(UNKNOWN_TASK_ID)
            val occurredAt = runCatching {
                OffsetDateTime.parse(root.path("occurred_at").asString())
            }.getOrDefault(UNKNOWN_OCCURRED_AT)
            RejectedMealContext(meal, taskId, occurredAt)
        }.getOrNull()
    }

    private fun digestRaw(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

    private fun syntheticEventId(payloadDigest: String): UUID {
        val bytes = payloadDigest.chunked(2).take(16).map { it.toInt(16).toByte() }.toByteArray()
        bytes[6] = ((bytes[6].toInt() and 0x0f) or 0x50).toByte()
        bytes[8] = ((bytes[8].toInt() and 0x3f) or 0x80).toByte()
        return ByteBuffer.wrap(bytes).let { UUID(it.long, it.long) }
    }

    private data class AiItem(
        val name: String,
        val weight: BigDecimal,
        val confidence: BigDecimal,
        val nutrients: List<Pair<String, BigDecimal>>,
    )

    private data class RejectedMealContext(
        val meal: NutritionResultRepository.ResultMeal,
        val taskId: UUID,
        val occurredAt: OffsetDateTime,
    )

    private companion object {
        val FAILURE_CODE = Regex("^[A-Z0-9_]{1,64}$")
        val FAILURE_CATEGORIES = setOf("transient", "permanent", "contract", "timeout", "cancelled")
        val RETRYABLE_CATEGORIES = setOf("transient", "timeout")
        val UNKNOWN_TASK_ID: UUID = UUID(0, 0)
        val UNKNOWN_OCCURRED_AT: OffsetDateTime = OffsetDateTime.ofInstant(Instant.EPOCH, ZoneOffset.UTC)
        const val UNKNOWN_EVENT_TYPE = "UNKNOWN_RESULT_EVENT"
        const val MAX_RAW_PAYLOAD_CHARS = 262_144
    }
}
