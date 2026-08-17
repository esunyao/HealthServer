package cn.esuny.nutrimemo.persistence

import cn.esuny.nutrimemo.model.FoodNutrientRecord
import cn.esuny.nutrimemo.model.FoodRecord
import cn.esuny.nutrimemo.model.MealImageRecord
import cn.esuny.nutrimemo.model.MealItemRecord
import cn.esuny.nutrimemo.model.MealRecord
import cn.esuny.nutrimemo.model.NutrientDefinition
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.core.RowMapper
import org.springframework.jdbc.core.SqlParameterValue
import org.springframework.stereotype.Repository
import java.math.BigDecimal
import java.sql.ResultSet
import java.sql.Types
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

@Repository
class NutriRepository(private val jdbc: JdbcTemplate) {
    private val foodMapper = RowMapper { rs: ResultSet, _: Int -> FoodRecord(rs.getLong("food_id"), rs.getObject("owner_user_id", UUID::class.java), rs.getString("scope"), rs.getString("name"), rs.getString("food_type"), rs.getString("brand_name"), rs.getBigDecimal("default_serving_g"), rs.getInt("version"), rs.getBoolean("active"), rs.getObject("created_at", OffsetDateTime::class.java), rs.getObject("updated_at", OffsetDateTime::class.java)) }
    private val nutrientMapper = RowMapper { rs: ResultSet, _: Int -> NutrientDefinition(rs.getLong("nutrient_id"), rs.getString("nutrient_code"), rs.getString("nutrient_name"), rs.getString("unit"), rs.getBoolean("active")) }
    private val mealMapper = RowMapper { rs: ResultSet, _: Int -> MealRecord(rs.getLong("meal_id"), rs.getObject("user_id", UUID::class.java), rs.getString("meal_type"), rs.getObject("consumed_at", OffsetDateTime::class.java), rs.getString("timezone"), rs.getObject("local_date", LocalDate::class.java), rs.getString("scenario"), rs.getString("entry_source"), rs.getString("notes"), rs.getString("status"), rs.getObject("idempotency_key", UUID::class.java), rs.getObject("created_at", OffsetDateTime::class.java), rs.getObject("updated_at", OffsetDateTime::class.java)) }
    private val itemMapper = RowMapper { rs: ResultSet, _: Int -> MealItemRecord(rs.getLong("item_id"), rs.getLong("meal_id"), rs.getInt("sequence_no"), rs.getObject("food_id", Long::class.javaObjectType), rs.getObject("food_version", Int::class.javaObjectType), rs.getString("food_name_snapshot"), rs.getBigDecimal("consumed_amount_g"), rs.getString("notes"), rs.getObject("created_at", OffsetDateTime::class.java)) }
    private val imageMapper = RowMapper { rs: ResultSet, _: Int -> MealImageRecord(rs.getLong("image_id"), rs.getLong("meal_id"), rs.getObject("user_id", UUID::class.java), rs.getString("bucket"), rs.getString("object_key"), rs.getString("content_type"), rs.getLong("content_length"), rs.getObject("captured_at", OffsetDateTime::class.java), rs.getString("status"), rs.getObject("confirmed_at", OffsetDateTime::class.java), rs.getObject("created_at", OffsetDateTime::class.java)) }

    fun nutrientsByCodes(codes: Collection<String>) = if (codes.isEmpty()) emptyList() else jdbc.query("SELECT nutrient_id,nutrient_code,nutrient_name,unit,active FROM nutri.nutrient_definitions WHERE nutrient_code IN (${codes.joinToString(",") { "?" }})", nutrientMapper, *codes.toTypedArray())
    fun food(id: Long) = jdbc.query("SELECT * FROM nutri.foods WHERE food_id=?", foodMapper, id).firstOrNull()
    fun aliases(foodId: Long): List<String> = jdbc.queryForList("SELECT alias_value FROM nutri.food_aliases WHERE food_id=? ORDER BY alias_id", String::class.java, foodId).filterNotNull()
    fun foodNutrients(foodId: Long): List<Triple<NutrientDefinition, BigDecimal, String>> = jdbc.query("SELECT n.nutrient_id,n.nutrient_code,n.nutrient_name,n.unit,n.active,v.amount_per_100g,v.data_source FROM nutri.food_nutrient_values v JOIN nutri.nutrient_definitions n ON n.nutrient_id=v.nutrient_id WHERE v.food_id=? ORDER BY n.display_order", { rs, _ -> Triple(NutrientDefinition(rs.getLong(1),rs.getString(2),rs.getString(3),rs.getString(4),rs.getBoolean(5)),rs.getBigDecimal(6),rs.getString(7)) }, foodId)
    fun searchFoods(userId: UUID, q: String?, type: String?, includeCustom: Boolean, offset: Int, limit: Int): List<FoodRecord> {
        val term = searchTerm(q)
        return jdbc.query(
            "SELECT * FROM nutri.foods f WHERE f.active AND (f.scope='public' OR (? AND f.owner_user_id=?)) " +
                "AND (CAST(? AS VARCHAR) IS NULL OR f.food_type=CAST(? AS VARCHAR)) " +
                "AND (CAST(? AS VARCHAR) IS NULL OR LOWER(f.name) LIKE CAST(? AS VARCHAR) OR " +
                "EXISTS(SELECT 1 FROM nutri.food_aliases a WHERE a.food_id=f.food_id AND a.normalized_value LIKE CAST(? AS VARCHAR))) " +
                "ORDER BY f.scope, f.name OFFSET ? LIMIT ?",
            foodMapper,
            boolean(includeCustom), uuid(userId), varchar(type), varchar(type), varchar(term), varchar(term), varchar(term), integer(offset), integer(limit)
        )
    }
    fun countFoods(userId: UUID, q: String?, type: String?, includeCustom: Boolean): Long {
        val term = searchTerm(q)
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM nutri.foods f WHERE f.active AND (f.scope='public' OR (? AND f.owner_user_id=?)) " +
                "AND (CAST(? AS VARCHAR) IS NULL OR f.food_type=CAST(? AS VARCHAR)) " +
                "AND (CAST(? AS VARCHAR) IS NULL OR LOWER(f.name) LIKE CAST(? AS VARCHAR) OR " +
                "EXISTS(SELECT 1 FROM nutri.food_aliases a WHERE a.food_id=f.food_id AND a.normalized_value LIKE CAST(? AS VARCHAR)))",
            Long::class.javaObjectType,
            boolean(includeCustom), uuid(userId), varchar(type), varchar(type), varchar(term), varchar(term), varchar(term)
        ) ?: 0
    }
    fun customFoods(userId: UUID, includeInactive: Boolean, offset: Int, limit: Int): List<FoodRecord> = jdbc.query(
        "SELECT * FROM nutri.foods WHERE owner_user_id=? AND scope='personal' AND (? OR active) ORDER BY active DESC,name OFFSET ? LIMIT ?",
        foodMapper, userId, includeInactive, offset, limit
    )
    fun countCustomFoods(userId: UUID, includeInactive: Boolean): Long = jdbc.queryForObject(
        "SELECT COUNT(*) FROM nutri.foods WHERE owner_user_id=? AND scope='personal' AND (? OR active)", Long::class.javaObjectType, userId, includeInactive
    ) ?: 0
    fun insertFood(food: FoodRecord) = jdbc.update("INSERT INTO nutri.foods(food_id,owner_user_id,scope,name,food_type,brand_name,default_serving_g,version,active) VALUES(?,?,?,?,?,?,?,?,?)",food.foodId,food.ownerUserId,food.scope,food.name,food.foodType,food.brandName,food.defaultServingG,food.version,food.active)
    fun updateFood(food: FoodRecord) = jdbc.update("UPDATE nutri.foods SET name=?,food_type=?,brand_name=?,default_serving_g=?,version=version+1 WHERE food_id=? AND owner_user_id=? AND scope='personal' AND active",food.name,food.foodType,food.brandName,food.defaultServingG,food.foodId,food.ownerUserId)
    fun deactivateFood(id: Long, userId: UUID) = jdbc.update("UPDATE nutri.foods SET active=false WHERE food_id=? AND owner_user_id=? AND scope='personal' AND active",id,userId)
    fun replaceAliases(foodId: Long, aliases: List<String>, ids: () -> Long) { jdbc.update("DELETE FROM nutri.food_aliases WHERE food_id=?",foodId); aliases.distinctBy{it.trim().lowercase()}.filter{it.isNotBlank()}.forEach { a -> jdbc.update("INSERT INTO nutri.food_aliases(alias_id,food_id,alias_type,alias_value,normalized_value) VALUES(?,?, 'alias', ?,?)",ids(),foodId,a.trim(),a.trim().lowercase()) } }
    fun replaceNutrients(foodId: Long, values: List<FoodNutrientRecord>) { jdbc.update("DELETE FROM nutri.food_nutrient_values WHERE food_id=?",foodId); values.forEach { v -> jdbc.update("INSERT INTO nutri.food_nutrient_values(food_id,nutrient_id,amount_per_100g,data_source) VALUES(?,?,?,?)",foodId,v.nutrientId,v.amountPer100g,v.dataSource) } }
    fun meal(id: Long, userId: UUID) = jdbc.query("SELECT * FROM nutri.meal_records WHERE meal_id=? AND user_id=?",mealMapper,id,userId).firstOrNull()
    fun mealByIdempotency(userId: UUID,key: UUID) = jdbc.query("SELECT * FROM nutri.meal_records WHERE user_id=? AND idempotency_key=?",mealMapper,userId,key).firstOrNull()
    fun insertMeal(m: MealRecord) = jdbc.update("INSERT INTO nutri.meal_records(meal_id,user_id,meal_type,consumed_at,timezone,local_date,scenario,entry_source,notes,status,idempotency_key) VALUES(?,?,?,?,?,?,?,?,?,'active',?)",m.mealId,m.userId,m.mealType,m.consumedAt,m.timezone,m.localDate,m.scenario,m.entrySource,m.notes,m.idempotencyKey)
    fun updateMeal(m: MealRecord) = jdbc.update("UPDATE nutri.meal_records SET meal_type=?,consumed_at=?,timezone=?,local_date=?,scenario=?,entry_source=?,notes=? WHERE meal_id=? AND user_id=? AND status='active'",m.mealType,m.consumedAt,m.timezone,m.localDate,m.scenario,m.entrySource,m.notes,m.mealId,m.userId)
    fun deleteMeal(id: Long,userId: UUID) = jdbc.update("UPDATE nutri.meal_records SET status='deleted',deleted_at=NOW() WHERE meal_id=? AND user_id=? AND status='active'",id,userId)
    fun replaceItems(mealId: Long, items: List<MealItemRecord>, snapshots: Map<Long,List<Pair<NutrientDefinition,BigDecimal>>>) { jdbc.update("DELETE FROM nutri.meal_items WHERE meal_id=?",mealId); items.forEach { i -> jdbc.update("INSERT INTO nutri.meal_items(item_id,meal_id,sequence_no,food_id,food_version,food_name_snapshot,consumed_amount_g,notes) VALUES(?,?,?,?,?,?,?,?)",i.itemId,i.mealId,i.sequenceNo,i.foodId,i.foodVersion,i.foodNameSnapshot,i.consumedAmountG,i.notes); snapshots.getValue(i.itemId).forEach{(n,a)->jdbc.update("INSERT INTO nutri.meal_item_nutrient_snapshots(item_id,nutrient_id,nutrient_code_snapshot,nutrient_name_snapshot,unit_snapshot,amount) VALUES(?,?,?,?,?,?)",i.itemId,n.nutrientId,n.nutrientCode,n.nutrientName,n.unit,a)} } }
    fun items(mealId: Long)=jdbc.query("SELECT * FROM nutri.meal_items WHERE meal_id=? ORDER BY sequence_no",itemMapper,mealId)
    fun itemNutrients(itemId: Long)=jdbc.query("SELECT nutrient_code_snapshot,nutrient_name_snapshot,unit_snapshot,amount FROM nutri.meal_item_nutrient_snapshots WHERE item_id=? ORDER BY nutrient_code_snapshot",{rs,_->arrayOf(rs.getString(1),rs.getString(2),rs.getString(3),rs.getBigDecimal(4))},itemId)
    fun images(mealId: Long)=jdbc.query("SELECT * FROM nutri.meal_images WHERE meal_id=? AND status <> 'deleted' ORDER BY image_id",imageMapper,mealId)
    fun insertImage(i: MealImageRecord)=jdbc.update("INSERT INTO nutri.meal_images(image_id,meal_id,user_id,bucket,object_key,content_type,content_length,captured_at,status) VALUES(?,?,?,?,?,?,?,?,?)",i.imageId,i.mealId,i.userId,i.bucket,i.objectKey,i.contentType,i.contentLength,i.capturedAt,i.status)
    fun image(id:Long,mealId:Long,userId:UUID)=jdbc.query("SELECT * FROM nutri.meal_images WHERE image_id=? AND meal_id=? AND user_id=?",imageMapper,id,mealId,userId).firstOrNull()
    fun imageByKey(key:String,mealId:Long,userId:UUID)=jdbc.query("SELECT * FROM nutri.meal_images WHERE object_key=? AND meal_id=? AND user_id=?",imageMapper,key,mealId,userId).firstOrNull()
    fun confirmImage(id:Long,capturedAt:OffsetDateTime?)=jdbc.update("UPDATE nutri.meal_images SET status='confirmed',confirmed_at=NOW(),captured_at=COALESCE(?,captured_at) WHERE image_id=? AND status='pending'",capturedAt,id)
    fun deleteImage(id:Long)=jdbc.update("UPDATE nutri.meal_images SET status='deleted',deleted_at=NOW() WHERE image_id=? AND status <> 'deleted'",id)
    fun listMeals(user: UUID, from: LocalDate, to: LocalDate, type: String?, offset: Int, limit: Int) = jdbc.query(
        "SELECT * FROM nutri.meal_records WHERE user_id=? AND status='active' AND local_date BETWEEN ? AND ? " +
            "AND (CAST(? AS VARCHAR) IS NULL OR meal_type=CAST(? AS VARCHAR)) ORDER BY consumed_at DESC OFFSET ? LIMIT ?",
        mealMapper,
        uuid(user), date(from), date(to), varchar(type), varchar(type), integer(offset), integer(limit)
    )
    fun countMeals(user: UUID, from: LocalDate, to: LocalDate, type: String?) = jdbc.queryForObject(
        "SELECT COUNT(*) FROM nutri.meal_records WHERE user_id=? AND status='active' AND local_date BETWEEN ? AND ? " +
            "AND (CAST(? AS VARCHAR) IS NULL OR meal_type=CAST(? AS VARCHAR))",
        Long::class.javaObjectType,
        uuid(user), date(from), date(to), varchar(type), varchar(type)
    ) ?: 0
    fun summaryRows(user:UUID,date:LocalDate)=jdbc.query("SELECT s.meal_count,s.updated_at,v.nutrient_code_snapshot,v.nutrient_name_snapshot,v.unit_snapshot,v.total_amount FROM nutri.daily_nutrition_summaries s LEFT JOIN nutri.daily_nutrition_values v ON v.summary_id=s.summary_id WHERE s.user_id=? AND s.local_date=? ORDER BY v.nutrient_code_snapshot",{rs,_->arrayOf(rs.getInt(1),rs.getObject(2,OffsetDateTime::class.java),rs.getString(3),rs.getString(4),rs.getString(5),rs.getBigDecimal(6))},user,date)
    fun mealBreakdownRows(user: UUID, date: LocalDate) = jdbc.query(
        "SELECT m.meal_type, COUNT(DISTINCT m.meal_id), s.nutrient_code_snapshot,s.nutrient_name_snapshot,s.unit_snapshot,SUM(s.amount) FROM nutri.meal_records m JOIN nutri.meal_items i ON i.meal_id=m.meal_id JOIN nutri.meal_item_nutrient_snapshots s ON s.item_id=i.item_id WHERE m.user_id=? AND m.local_date=? AND m.status='active' GROUP BY m.meal_type,s.nutrient_code_snapshot,s.nutrient_name_snapshot,s.unit_snapshot ORDER BY m.meal_type,s.nutrient_code_snapshot",
        {rs,_->arrayOf(rs.getString(1),rs.getInt(2),rs.getString(3),rs.getString(4),rs.getString(5),rs.getBigDecimal(6))}, user, date
    )
    fun recalculateDaily(user:UUID,date:LocalDate,summaryId:Long) {
        val count=jdbc.queryForObject("SELECT COUNT(*) FROM nutri.meal_records WHERE user_id=? AND local_date=? AND status='active'",Int::class.javaObjectType,user,date)?:0
        if(count==0){jdbc.update("DELETE FROM nutri.daily_nutrition_summaries WHERE user_id=? AND local_date=?",user,date);return}
        jdbc.update("INSERT INTO nutri.daily_nutrition_summaries(summary_id,user_id,local_date,meal_count,last_recalculated_at) VALUES(?,?,?,?,NOW()) ON CONFLICT(user_id,local_date) DO UPDATE SET meal_count=EXCLUDED.meal_count,last_recalculated_at=NOW()",summaryId,user,date,count)
        val id=jdbc.queryForObject("SELECT summary_id FROM nutri.daily_nutrition_summaries WHERE user_id=? AND local_date=?",Long::class.javaObjectType,user,date)!!
        jdbc.update("DELETE FROM nutri.daily_nutrition_values WHERE summary_id=?",id)
        jdbc.update("INSERT INTO nutri.daily_nutrition_values(summary_id,nutrient_id,nutrient_code_snapshot,nutrient_name_snapshot,unit_snapshot,total_amount) SELECT ?,x.nutrient_id,x.nutrient_code_snapshot,x.nutrient_name_snapshot,x.unit_snapshot,SUM(x.amount) FROM nutri.meal_item_nutrient_snapshots x JOIN nutri.meal_items i ON i.item_id=x.item_id JOIN nutri.meal_records m ON m.meal_id=i.meal_id WHERE m.user_id=? AND m.local_date=? AND m.status='active' GROUP BY x.nutrient_id,x.nutrient_code_snapshot,x.nutrient_name_snapshot,x.unit_snapshot",id,user,date)
    }

    private fun searchTerm(q: String?) = q?.trim()?.lowercase()?.takeIf { it.isNotBlank() }?.let { "%$it%" }
    private fun boolean(value: Boolean) = SqlParameterValue(Types.BOOLEAN, value)
    private fun uuid(value: UUID) = SqlParameterValue(Types.OTHER, value)
    private fun varchar(value: String?) = SqlParameterValue(Types.VARCHAR, value)
    private fun date(value: LocalDate) = SqlParameterValue(Types.DATE, value)
    private fun integer(value: Int) = SqlParameterValue(Types.INTEGER, value)
}
