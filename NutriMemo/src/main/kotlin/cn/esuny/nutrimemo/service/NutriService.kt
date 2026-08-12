package cn.esuny.nutrimemo.service

import cn.esuny.nutrimemo.config.OssProperties
import cn.esuny.nutrimemo.handler.BusinessException
import cn.esuny.nutrimemo.identity.AuthenticatedUser
import cn.esuny.nutrimemo.model.*
import cn.esuny.nutrimemo.persistence.NutriRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.model.HeadObjectRequest
import software.amazon.awssdk.services.s3.model.PutObjectRequest
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest
import java.math.BigDecimal
import java.math.RoundingMode
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.UUID

private val REQUIRED_NUTRIENTS = setOf("ENERGY_KCAL", "PROTEIN", "FAT", "CARBOHYDRATE")
private val FOOD_TYPES = setOf("ingredient", "dish", "packaged_food", "beverage", "supplement")
private val MEAL_TYPES = setOf("breakfast", "lunch", "dinner", "snack", "other")
private val ENTRY_SOURCES = setOf("manual", "photo_placeholder", "import")

@Service
class NutriService(
    private val repository: NutriRepository,
    private val ids: SnowflakeIdGenerator,
    private val s3Client: S3Client,
    private val s3Presigner: S3Presigner,
    private val oss: OssProperties
) {
    fun searchFoods(user: AuthenticatedUser, q: String?, type: String?, includeCustom: Boolean, page: Int, pageSize: Int): PageResult<FoodView> {
        type?.let { requireAllowed("foodType", it, FOOD_TYPES) }
        validPage(page, pageSize)
        return PageResult(repository.searchFoods(user.userId, q, type, includeCustom, (page - 1) * pageSize, pageSize).map(::foodView), page, pageSize, repository.countFoods(user.userId, q, type, includeCustom))
    }

    fun customFoods(user: AuthenticatedUser, includeInactive: Boolean, page: Int, pageSize: Int): PageResult<FoodView> {
        validPage(page, pageSize)
        return PageResult(repository.customFoods(user.userId, includeInactive, (page - 1) * pageSize, pageSize).map(::foodView), page, pageSize, repository.countCustomFoods(user.userId, includeInactive))
    }

    fun food(user: AuthenticatedUser, id: Long): FoodView = visibleFood(user.userId, id).let(::foodView)

    @Transactional
    fun createCustomFood(user: AuthenticatedUser, request: CustomFoodRequest): FoodView {
        val normalized = validateFoodRequest(request)
        val now = OffsetDateTime.now()
        val record = FoodRecord(ids.nextId(), user.userId, "personal", normalized.name, normalized.foodType, normalized.brandName, normalized.defaultServingG, 1, true, now, now)
        repository.insertFood(record)
        writeFoodDetails(record.foodId, normalized)
        return foodView(record)
    }

    @Transactional
    fun updateCustomFood(user: AuthenticatedUser, id: Long, request: CustomFoodRequest): FoodView {
        val current = repository.food(id)?.takeIf { it.ownerUserId == user.userId && it.scope == "personal" && it.active }
            ?: notFound()
        val normalized = validateFoodRequest(request)
        if (repository.updateFood(current.copy(name = normalized.name, foodType = normalized.foodType, brandName = normalized.brandName, defaultServingG = normalized.defaultServingG)) == 0) notFound()
        writeFoodDetails(id, normalized)
        return foodView(visibleFood(user.userId, id))
    }

    fun deactivateCustomFood(user: AuthenticatedUser, id: Long) { if (repository.deactivateFood(id, user.userId) == 0) notFound() }

    fun meals(user: AuthenticatedUser, from: LocalDate, to: LocalDate, type: String?, page: Int, pageSize: Int): PageResult<MealView> {
        if (to < from) throw BusinessException(400, "dateTo 不能早于 dateFrom")
        type?.let { requireAllowed("mealType", it, MEAL_TYPES) }; validPage(page, pageSize)
        val values = repository.listMeals(user.userId, from, to, type, (page - 1) * pageSize, pageSize).map(::mealView)
        return PageResult(values, page, pageSize, repository.countMeals(user.userId, from, to, type))
    }

    fun meal(user: AuthenticatedUser, id: Long): MealView = repository.meal(id, user.userId)?.let(::mealView) ?: notFound()

    @Transactional
    fun createMeal(user: AuthenticatedUser, idempotency: UUID, request: MealUpsertRequest): MealView {
        repository.mealByIdempotency(user.userId, idempotency)?.let { return mealView(it) }
        validateMeal(request)
        val localDate = localDate(request)
        val now = OffsetDateTime.now()
        val meal = MealRecord(ids.nextId(), user.userId, request.mealType, request.consumedAt, request.timezone, localDate, request.scenario?.trim()?.ifBlank { null }, request.entrySource, request.notes?.trim()?.ifBlank { null }, "active", idempotency, now, now)
        repository.insertMeal(meal); replaceMealItems(user.userId, meal.mealId, request)
        repository.recalculateDaily(user.userId, localDate, ids.nextId())
        return mealView(repository.meal(meal.mealId, user.userId)!!)
    }

    @Transactional
    fun replaceMeal(user: AuthenticatedUser, id: Long, request: MealUpsertRequest): MealView {
        val current = repository.meal(id, user.userId)?.takeIf { it.status == "active" } ?: notFound()
        validateMeal(request); val newDate = localDate(request)
        repository.updateMeal(current.copy(mealType = request.mealType, consumedAt = request.consumedAt, timezone = request.timezone, localDate = newDate, scenario = request.scenario?.trim()?.ifBlank { null }, entrySource = request.entrySource, notes = request.notes?.trim()?.ifBlank { null }))
        replaceMealItems(user.userId, id, request)
        repository.recalculateDaily(user.userId, current.localDate, ids.nextId())
        if (newDate != current.localDate) repository.recalculateDaily(user.userId, newDate, ids.nextId())
        return mealView(repository.meal(id, user.userId)!!)
    }

    @Transactional
    fun deleteMeal(user: AuthenticatedUser, id: Long) {
        val current = repository.meal(id, user.userId)?.takeIf { it.status == "active" } ?: notFound()
        if (repository.deleteMeal(id, user.userId) == 0) notFound()
        repository.recalculateDaily(user.userId, current.localDate, ids.nextId())
    }

    @Transactional
    fun presignImage(user: AuthenticatedUser, mealId: Long, request: MealImagePresignRequest): PresignedUrlView {
        repository.meal(mealId, user.userId)?.takeIf { it.status == "active" } ?: notFound()
        if (request.contentType !in oss.allowedContentTypes || request.contentLength > oss.maxFileSize) throw BusinessException(400, "图片类型或大小不符合要求")
        val extension = request.fileName.substringAfterLast('.', "jpg").lowercase().replace(Regex("[^a-z0-9]"), "").ifBlank { "jpg" }
        val key = "nutri/${user.userId}/$mealId/${UUID.randomUUID()}.$extension"
        val image = MealImageRecord(ids.nextId(), mealId, user.userId, oss.bucket, key, request.contentType, request.contentLength, request.capturedAt, "pending", null, OffsetDateTime.now())
        repository.insertImage(image)
        val signed = s3Presigner.presignPutObject(PutObjectPresignRequest.builder().signatureDuration(oss.presignedExpiration).putObjectRequest(PutObjectRequest.builder().bucket(oss.bucket).key(key).contentType(request.contentType).contentLength(request.contentLength).build()).build())
        return PresignedUrlView(signed.url().toString(), key, oss.presignedExpiration.toSeconds(), mapOf("Content-Type" to request.contentType))
    }

    fun confirmImage(user: AuthenticatedUser, mealId: Long, request: MealImageConfirmRequest): MealImageView {
        repository.meal(mealId, user.userId)?.takeIf { it.status == "active" } ?: notFound()
        val image = repository.imageByKey(request.objectKey, mealId, user.userId)?.takeIf { it.status == "pending" }
            ?: throw BusinessException(409, "图片未处于待确认状态", HttpStatus.CONFLICT)
        val expectedPrefix = "nutri/${user.userId}/$mealId/"
        if (!image.objectKey.startsWith(expectedPrefix)) throw BusinessException(403, "对象 key 不属于当前餐次", HttpStatus.FORBIDDEN)
        val head = try { s3Client.headObject(HeadObjectRequest.builder().bucket(oss.bucket).key(image.objectKey).build()) } catch (_: Exception) { throw BusinessException(404, "图片不存在或上传失败", HttpStatus.NOT_FOUND) }
        if (head.contentType() != image.contentType || head.contentLength() == null || head.contentLength() > oss.maxFileSize) throw BusinessException(400, "图片类型或大小不符合要求")
        if (repository.confirmImage(image.imageId, request.capturedAt) == 0) throw BusinessException(409, "图片已被确认或删除", HttpStatus.CONFLICT)
        return imageView(repository.image(image.imageId, mealId, user.userId)!!)
    }

    fun deleteImage(user: AuthenticatedUser, mealId: Long, imageId: Long) {
        val image = repository.image(imageId, mealId, user.userId)?.takeIf { it.status != "deleted" } ?: notFound()
        repository.deleteImage(image.imageId)
    }

    fun dailySummary(user: AuthenticatedUser, date: LocalDate): DailySummaryView = daily(user.userId, date)
    fun dailyTrend(user: AuthenticatedUser, from: LocalDate, to: LocalDate): DailyTrendView {
        if (to < from || java.time.temporal.ChronoUnit.DAYS.between(from, to) > 366) throw BusinessException(400, "日期范围无效")
        val days = generateSequence(from) { if (it < to) it.plusDays(1) else null }.map { daily(user.userId, it) }.toList()
        return DailyTrendView(from, to, days)
    }

    private fun daily(userId: UUID, date: LocalDate): DailySummaryView {
        val rows = repository.summaryRows(userId, date)
        if (rows.isEmpty()) return DailySummaryView(date, 0, emptyList(), emptyList(), OffsetDateTime.now())
        val nutrients = rows.filter { it[2] != null }.map { NutrientValue(it[2] as String, it[3] as String, it[4] as String, it[5] as BigDecimal) }
        val breakdown = repository.mealBreakdownRows(userId, date).groupBy { it[0] as String }.map { (mealType, values) ->
            DailyMealBreakdown(mealType, values.first()[1] as Int, values.map { NutrientValue(it[2] as String, it[3] as String, it[4] as String, it[5] as BigDecimal) })
        }
        return DailySummaryView(date, rows.first()[0] as Int, nutrients, breakdown, rows.first()[1] as OffsetDateTime)
    }

    private fun validateFoodRequest(request: CustomFoodRequest): CustomFoodRequest {
        requireAllowed("foodType", request.foodType, FOOD_TYPES)
        val codes = request.nutrients.map { it.nutrientCode.trim().uppercase() }
        if (codes.size != codes.toSet().size) throw BusinessException(400, "营养素编码不能重复")
        if (!codes.containsAll(REQUIRED_NUTRIENTS)) throw BusinessException(400, "必须包含能量、蛋白质、脂肪和碳水化合物")
        val known = repository.nutrientsByCodes(codes)
        if (known.size != codes.size || known.any { !it.active }) throw BusinessException(400, "包含不存在或已停用的营养素编码")
        return request.copy(name = request.name.trim(), foodType = request.foodType.trim(), aliases = request.aliases.map { it.trim() }, nutrients = request.nutrients.map { it.copy(nutrientCode = it.nutrientCode.trim().uppercase()) })
    }

    private fun writeFoodDetails(foodId: Long, request: CustomFoodRequest) {
        val definitions = repository.nutrientsByCodes(request.nutrients.map { it.nutrientCode }).associateBy { it.nutrientCode }
        repository.replaceAliases(foodId, request.aliases, ids::nextId)
        repository.replaceNutrients(foodId, request.nutrients.map { FoodNutrientRecord(foodId, definitions.getValue(it.nutrientCode).nutrientId, it.amount) })
    }

    private fun validateMeal(request: MealUpsertRequest) {
        requireAllowed("mealType", request.mealType, MEAL_TYPES); requireAllowed("entrySource", request.entrySource, ENTRY_SOURCES)
        try { ZoneId.of(request.timezone) } catch (_: Exception) { throw BusinessException(400, "timezone 必须是有效 IANA 时区") }
        if (request.consumedAt.isAfter(OffsetDateTime.now().plusMinutes(5))) throw BusinessException(400, "用餐时间不能晚于当前时间")
        if (request.items.map { it.foodId }.size != request.items.map { it.foodId }.toSet().size) throw BusinessException(400, "同一餐次不能重复添加同一食物")
    }

    private fun localDate(request: MealUpsertRequest) = request.consumedAt.atZoneSameInstant(ZoneId.of(request.timezone)).toLocalDate()
    private fun replaceMealItems(userId: UUID, mealId: Long, request: MealUpsertRequest) {
        val items = request.items.mapIndexed { i, input ->
            val food = visibleFood(userId, input.foodId)
            MealItemRecord(ids.nextId(), mealId, i + 1, food.foodId, food.version, input.displayName?.trim()?.ifBlank { null } ?: food.name, input.consumedAmountG, input.notes?.trim()?.ifBlank { null }, OffsetDateTime.now())
        }
        val snapshots = items.associate { item ->
            val foodNutrients = repository.foodNutrients(item.foodId!!)
            if (foodNutrients.isEmpty()) throw BusinessException(400, "食物缺少营养成分，不能用于餐次")
            item.itemId to foodNutrients.map { (nutrient, amount, _) -> nutrient to amount.multiply(item.consumedAmountG).divide(BigDecimal(100), 6, RoundingMode.HALF_UP) }
        }
        repository.replaceItems(mealId, items, snapshots)
    }
    private fun visibleFood(userId: UUID, id: Long) = repository.food(id)?.takeIf { it.active && (it.scope == "public" || it.ownerUserId == userId) } ?: notFound()
    private fun foodView(f: FoodRecord) = FoodView(f.foodId,f.scope,f.name,f.foodType,f.brandName,f.defaultServingG,repository.aliases(f.foodId),f.active,repository.foodNutrients(f.foodId).map{NutrientValue(it.first.nutrientCode,it.first.nutrientName,it.first.unit,it.second)},f.version,f.createdAt,f.updatedAt)
    private fun mealView(m: MealRecord): MealView { val items=repository.items(m.mealId).map { i -> MealItemView(i.itemId,i.sequenceNo,i.foodId,i.foodVersion,i.foodNameSnapshot,i.consumedAmountG,i.notes,repository.itemNutrients(i.itemId).map{NutrientValue(it[0] as String,it[1] as String,it[2] as String,it[3] as BigDecimal)},i.createdAt) }; val nutrients=items.flatMap{it.nutrientSnapshots}.groupBy{Triple(it.nutrientCode,it.nutrientName,it.unit)}.map{(k,v)->NutrientValue(k.first,k.second,k.third,v.fold(BigDecimal.ZERO){a,n->a+n.amount})}; return MealView(m.mealId,m.mealType,m.consumedAt,m.timezone,m.localDate,m.scenario,m.entrySource,m.notes,m.status,items,repository.images(m.mealId).map(::imageView),nutrients,m.createdAt,m.updatedAt) }
    private fun imageView(i: MealImageRecord)=MealImageView(i.imageId,i.objectKey,i.contentType,i.capturedAt,i.status,i.createdAt)
    private fun requireAllowed(field:String,value:String,allowed:Set<String>) { if(value !in allowed) throw BusinessException(400,"$field 值无效") }
    private fun validPage(page:Int,size:Int) { if(page < 1 || size !in 1..100) throw BusinessException(400,"分页参数无效") }
    private fun notFound(): Nothing = throw BusinessException(404,"资源不存在",HttpStatus.NOT_FOUND)
}
