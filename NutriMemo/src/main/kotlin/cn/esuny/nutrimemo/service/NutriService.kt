package cn.esuny.nutrimemo.service

import cn.esuny.nutrimemo.config.CaptureProperties
import cn.esuny.nutrimemo.config.OssProperties
import cn.esuny.nutrimemo.handler.BusinessException
import cn.esuny.nutrimemo.identity.AuthenticatedUser
import cn.esuny.nutrimemo.model.*
import cn.esuny.nutrimemo.persistence.NutriRepository
import org.springframework.http.HttpStatus
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest
import software.amazon.awssdk.services.s3.model.HeadObjectRequest
import software.amazon.awssdk.services.s3.model.PutObjectRequest
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest
import java.math.BigDecimal
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.UUID

private val MEAL_TYPES = setOf("breakfast", "lunch", "dinner", "snack", "other")

@Service
class NutriService(
    private val repository: NutriRepository,
    private val ids: SnowflakeIdGenerator,
    private val s3Client: S3Client,
    private val s3Presigner: S3Presigner,
    private val oss: OssProperties,
    private val capture: CaptureProperties
) {
    fun capturePolicy() = CapturePolicyView(10, oss.maxFileSize, oss.allowedContentTypes, capture.sessionTtl.seconds)

    @Transactional
    fun createCaptureSession(user: AuthenticatedUser, requestId: UUID, request: CaptureSessionCreateRequest): CaptureSessionView {
        validateTimezone(request.timezone)
        repository.sessionByRequest(user.userId, requestId)?.let { return captureView(it) }
        val now = OffsetDateTime.now()
        val record = CaptureSessionRecord(UUID.randomUUID(), user.userId, requestId, "created", request.timezone.trim(), 10, now.plus(capture.sessionTtl), null, now, now)
        repository.insertSession(record)
        return captureView(repository.session(record.captureSessionId, user.userId)!!)
    }

    fun captureSession(user: AuthenticatedUser, id: UUID) = captureView(repository.session(id, user.userId) ?: notFound())

    @Transactional
    fun presignCaptureImage(user: AuthenticatedUser, sessionId: UUID, request: CaptureImagePresignRequest): PresignedUrlView {
        val session = mutableSession(user, sessionId)
        if (request.contentType !in oss.allowedContentTypes || request.contentLength > oss.maxFileSize) bad("图片类型或大小不符合要求")
        val current = repository.images(sessionId)
        val reusable = current.firstOrNull { it.status == "deleted" }
        val slot = reusable?.slotNo ?: (1..session.maxImageCount).firstOrNull { candidate -> current.none { it.slotNo == candidate } } ?: bad("图片数量已达上限")
        val extension = request.fileName.substringAfterLast('.', "jpg").lowercase().replace(Regex("[^a-z0-9]"), "").ifBlank { "jpg" }
        val key = "nutri/${user.userId}/capture/$sessionId/${UUID.randomUUID()}.$extension"
        val imageId = reusable?.imageId ?: ids.nextId()
        if (reusable == null) repository.insertImage(CaptureImageRecord(imageId, sessionId, slot, oss.bucket, key, request.contentType, request.contentLength, request.capturedAt, "pending", null, OffsetDateTime.now()))
        else repository.reuseDeletedImage(imageId, key, request.contentType, request.contentLength, request.capturedAt)
        if (session.status == "created") repository.updateSessionStatus(sessionId, user.userId, "uploading")
        val signed = s3Presigner.presignPutObject(PutObjectPresignRequest.builder().signatureDuration(oss.presignedExpiration).putObjectRequest(PutObjectRequest.builder().bucket(oss.bucket).key(key).contentType(request.contentType).contentLength(request.contentLength).build()).build())
        return PresignedUrlView(imageId.toString(), signed.url().toString(), key, oss.presignedExpiration.seconds, mapOf("Content-Type" to request.contentType))
    }

    @Transactional
    fun confirmCaptureImage(user: AuthenticatedUser, sessionId: UUID, imageId: Long): CaptureImageView {
        mutableSession(user, sessionId)
        val image = repository.image(imageId, sessionId)?.takeIf { it.status == "pending" } ?: conflict("图片未处于待确认状态")
        val head = try { s3Client.headObject(HeadObjectRequest.builder().bucket(oss.bucket).key(image.objectKey).build()) } catch (_: Exception) { throw BusinessException(404, "图片不存在或上传失败", HttpStatus.NOT_FOUND) }
        if (head.contentType() != image.contentType || head.contentLength() == null || head.contentLength() > oss.maxFileSize) bad("图片类型或大小不符合要求")
        if (repository.confirmImage(imageId) == 0) conflict("图片状态已变化")
        return imageView(repository.image(imageId, sessionId)!!)
    }

    @Transactional
    fun deleteCaptureImage(user: AuthenticatedUser, sessionId: UUID, imageId: Long) {
        mutableSession(user, sessionId)
        val image = repository.image(imageId, sessionId)?.takeIf { it.status in setOf("pending", "confirmed") } ?: notFound()
        if (repository.deleteImage(imageId) == 0) conflict("图片状态已变化")
        deleteObject(image)
    }

    @Transactional
    fun submitCapture(user: AuthenticatedUser, sessionId: UUID): CaptureSessionView {
        val session = mutableSession(user, sessionId)
        if (repository.confirmedImageCount(sessionId) == 0) bad("请至少确认一张图片后再开始识别")
        if (session.status !in setOf("created", "uploading")) conflict("当前会话不能提交识别")
        repository.updateSessionStatus(sessionId, user.userId, "ready_for_analysis", true)
        repository.insertOutbox(UUID.randomUUID(), sessionId)
        return captureView(repository.session(sessionId, user.userId)!!)
    }

    @Transactional
    fun retryCapture(user: AuthenticatedUser, sessionId: UUID): CaptureSessionView {
        val session = repository.sessionForUpdate(sessionId, user.userId) ?: notFound()
        if (session.status != "failed") conflict("仅识别失败的会话可以重试")
        if (repository.confirmedImageCount(sessionId) == 0) bad("会话没有可用于重试的已确认图片")
        repository.updateSessionStatus(sessionId, user.userId, "ready_for_analysis", true)
        repository.insertOutbox(UUID.randomUUID(), sessionId)
        return captureView(repository.session(sessionId, user.userId)!!)
    }

    @Transactional
    fun cancelCapture(user: AuthenticatedUser, sessionId: UUID) {
        val session = repository.sessionForUpdate(sessionId, user.userId) ?: notFound()
        val images = repository.images(session.captureSessionId).filter { it.status in setOf("pending", "confirmed") }
        if (repository.cancelSession(sessionId, user.userId) == 0) conflict("当前会话不能取消")
        images.forEach { repository.deleteImage(it.imageId); deleteObject(it) }
    }

    fun meals(user: AuthenticatedUser, from: LocalDate, to: LocalDate, type: String?, q: String?, page: Int, pageSize: Int): PageResult<MealHistoryItemView> {
        validRange(from, to); type?.let { validMealType(it) }; validPage(page, pageSize)
        val keyword = q?.trim()?.takeIf { it.isNotEmpty() }?.let { "%$it%" }
        val meals = repository.listMeals(user.userId, from, to, type, keyword, (page - 1) * pageSize, pageSize).map { meal -> MealHistoryItemView(meal.mealId.toString(), meal.mealType, meal.consumedAt, meal.localDate, meal.notes, repository.mealNutrients(meal.mealId)) }
        return PageResult(meals, page, pageSize, repository.countMeals(user.userId, from, to, type, keyword))
    }

    fun meal(user: AuthenticatedUser, id: Long) = mealView(repository.meal(id, user.userId) ?: notFound())

    @Transactional
    fun replaceMeal(user: AuthenticatedUser, id: Long, request: MealCorrectionRequest): MealView {
        val current = repository.meal(id, user.userId)?.takeIf { it.status == "active" } ?: notFound()
        validMealType(request.mealType); validateTimezone(request.timezone)
        if (request.consumedAt.isAfter(OffsetDateTime.now().plusMinutes(5))) bad("用餐时间不能晚于当前时间")
        val existingItemIds = repository.items(id).map { it.itemId }.toSet()
        val requestItemIds = request.items.mapNotNull { it.itemId }
        if (requestItemIds.size != requestItemIds.toSet().size || requestItemIds.any { it !in existingItemIds }) bad("餐食条目不属于当前餐次")
        request.items.forEach { item ->
            val itemCodes = item.nutrients.map { it.nutrientCode.trim().uppercase() }
            if (itemCodes.size != itemCodes.toSet().size) bad("同一条目中的营养素编码不能重复")
        }
        val codes = request.items.flatMap { it.nutrients }.map { it.nutrientCode.trim().uppercase() }
        val definitions = repository.nutrientsByCodes(codes).associateBy { it.nutrientCode }
        if (definitions.size != codes.toSet().size || definitions.values.any { !it.active }) bad("包含不存在或已停用的营养素编码")
        val localDate = request.consumedAt.atZoneSameInstant(ZoneId.of(request.timezone)).toLocalDate()
        val updated = current.copy(mealType = request.mealType, consumedAt = request.consumedAt, timezone = request.timezone.trim(), localDate = localDate, notes = request.notes?.trim()?.ifBlank { null })
        repository.updateMeal(updated)
        val items = request.items.mapIndexed { index, item -> MealItemRecord(item.itemId ?: ids.nextId(), id, index + 1, item.displayName.trim(), item.estimatedWeightG, null, "manual", true, item.notes?.trim()?.ifBlank { null }) }
        val values = items.zip(request.items).associate { (item, input) -> item.itemId to input.nutrients.map { nutrient -> definitions.getValue(nutrient.nutrientCode.trim().uppercase()) to nutrient.amount } }
        repository.replaceItems(id, items, values)
        repository.recalculateDaily(user.userId, current.localDate, ids.nextId())
        if (localDate != current.localDate) repository.recalculateDaily(user.userId, localDate, ids.nextId())
        return meal(user, id)
    }

    @Transactional
    fun deleteMeal(user: AuthenticatedUser, id: Long) {
        val current = repository.meal(id, user.userId)?.takeIf { it.status == "active" } ?: notFound()
        repository.deleteMeal(id, user.userId)
        repository.recalculateDaily(user.userId, current.localDate, ids.nextId())
    }

    fun dailySummary(user: AuthenticatedUser, date: LocalDate) = daily(user.userId, date)
    fun dailyTrend(user: AuthenticatedUser, from: LocalDate, to: LocalDate): DailyTrendView {
        validRange(from, to)
        return DailyTrendView(from, to, generateSequence(from) { if (it < to) it.plusDays(1) else null }.map { daily(user.userId, it) }.toList())
    }

    @Scheduled(fixedDelayString = "\${nutri.capture.cleanup-interval:15m}")
    @Transactional
    fun expireCaptureSessions() {
        repository.expiredSessions(OffsetDateTime.now()).forEach { session ->
            val images = repository.images(session.captureSessionId).filter { it.status in setOf("pending", "confirmed") }
            if (repository.expireSession(session.captureSessionId) > 0) { repository.expireImages(session.captureSessionId); images.forEach(::deleteObject) }
        }
    }

    private fun mutableSession(user: AuthenticatedUser, id: UUID): CaptureSessionRecord {
        val session = repository.sessionForUpdate(id, user.userId) ?: notFound()
        if (session.expiresAt.isBefore(OffsetDateTime.now())) conflict("采集会话已过期")
        if (session.status !in setOf("created", "uploading")) conflict("当前会话不能修改图片")
        return session
    }
    private fun captureView(value: CaptureSessionRecord) = CaptureSessionView(value.captureSessionId, value.status, value.timezone, value.maxImageCount, value.expiresAt, value.analysisRequestedAt, repository.images(value.captureSessionId).map(::imageView), value.createdAt, value.updatedAt)
    private fun imageView(value: CaptureImageRecord) = CaptureImageView(value.imageId.toString(), value.slotNo, value.objectKey, value.contentType, value.contentLength, value.capturedAt, value.status, value.createdAt)
    private fun mealView(value: MealRecord): MealView { val items = repository.items(value.mealId).map { item -> MealItemView(item.itemId.toString(), item.sequenceNo, item.displayName, item.estimatedWeightG, item.confidence, item.dataSource, item.userCorrected, item.notes, repository.itemNutrients(item.itemId)) }; return MealView(value.mealId.toString(), value.captureSessionId, value.mealType, value.consumedAt, value.timezone, value.localDate, value.notes, items, repository.mealNutrients(value.mealId), value.createdAt, value.updatedAt) }
    private fun daily(userId: UUID, date: LocalDate): DailySummaryView { val rows = repository.summaryRows(userId, date); if (rows.isEmpty()) return DailySummaryView(date, 0, emptyList(), emptyList(), OffsetDateTime.now()); val nutrients = rows.filter { it[2] != null }.map { NutrientValue(it[2] as String, it[3] as String, it[4] as String, it[5] as BigDecimal) }; val breakdown = repository.breakdownRows(userId, date).groupBy { it[0] as String }.map { (type, values) -> DailyMealBreakdown(type, values.first()[1] as Int, values.map { NutrientValue(it[2] as String, it[3] as String, it[4] as String, it[5] as BigDecimal) }) }; return DailySummaryView(date, rows.first()[0] as Int, nutrients, breakdown, rows.first()[1] as OffsetDateTime) }
    private fun deleteObject(image: CaptureImageRecord) { try { s3Client.deleteObject(DeleteObjectRequest.builder().bucket(image.bucket).key(image.objectKey).build()) } catch (_: Exception) { } }
    private fun validateTimezone(value: String) { try { ZoneId.of(value) } catch (_: Exception) { bad("timezone 必须是有效 IANA 时区") } }
    private fun validMealType(value: String) { if (value !in MEAL_TYPES) bad("mealType 值无效") }
    private fun validRange(from: LocalDate, to: LocalDate) { if (to < from || java.time.temporal.ChronoUnit.DAYS.between(from, to) > 366) bad("日期范围无效") }
    private fun validPage(page: Int, size: Int) { if (page < 1 || size !in 1..100) bad("分页参数无效") }
    private fun bad(message: String): Nothing = throw BusinessException(400, message)
    private fun conflict(message: String): Nothing = throw BusinessException(409, message, HttpStatus.CONFLICT)
    private fun notFound(): Nothing = throw BusinessException(404, "资源不存在", HttpStatus.NOT_FOUND)
}
