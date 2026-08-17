package cn.esuny.nutrimemo.persistence

import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.junit.jupiter.api.Test
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.core.RowMapper
import java.math.BigDecimal
import java.sql.ResultSet
import java.time.OffsetDateTime
import kotlin.test.assertEquals
import kotlin.test.assertNull

class NutriRepositoryResultMappingTest {
    @Test
    fun `meal item mapper reads present numeric values with boxed JDBC types`() {
        val resultSet = mealItemResultSet(foodId = 21L, foodVersion = 3)

        val item = NutriRepository(ItemMappingJdbcTemplate(resultSet)).items(10L).single()

        assertEquals(21L, item.foodId)
        assertEquals(3, item.foodVersion)
        verify { resultSet.getObject("food_id", Long::class.javaObjectType) }
        verify { resultSet.getObject("food_version", Int::class.javaObjectType) }
    }

    @Test
    fun `meal item mapper preserves null numeric values`() {
        val resultSet = mealItemResultSet(foodId = null, foodVersion = null)

        val item = NutriRepository(ItemMappingJdbcTemplate(resultSet)).items(10L).single()

        assertNull(item.foodId)
        assertNull(item.foodVersion)
    }

    private fun mealItemResultSet(foodId: Long?, foodVersion: Int?): ResultSet = mockk {
        every { getLong("item_id") } returns 1L
        every { getLong("meal_id") } returns 10L
        every { getInt("sequence_no") } returns 1
        every { getObject("food_id", Long::class.javaObjectType) } returns foodId
        every { getObject("food_version", Int::class.javaObjectType) } returns foodVersion
        every { getString("food_name_snapshot") } returns "鸡肉卷"
        every { getBigDecimal("consumed_amount_g") } returns BigDecimal("100")
        every { getString("notes") } returns null
        every { getObject("created_at", OffsetDateTime::class.java) } returns OffsetDateTime.parse("2026-08-14T00:00:00Z")
    }
}

private class ItemMappingJdbcTemplate(private val resultSet: ResultSet) : JdbcTemplate() {
    override fun <T : Any?> query(sql: String, rowMapper: RowMapper<T>, vararg args: Any?): List<T> =
        listOf(rowMapper.mapRow(resultSet, 0))
}
