package cn.esuny.nutrimemo.persistence

import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.core.RowMapper
import org.springframework.jdbc.core.SqlParameterValue
import java.sql.Types
import java.time.LocalDate
import java.util.UUID
import kotlin.test.assertContains
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class NutriRepositoryParameterBindingTest {
    private val jdbc = RecordingJdbcTemplate()
    private val repository = NutriRepository(jdbc)
    private val userId = UUID.fromString("8c4af8cd-7c3d-46ac-8f57-6c798cffc8ea")
    private val dateFrom = LocalDate.of(2026, 8, 1)
    private val dateTo = LocalDate.of(2026, 8, 7)

    @BeforeEach
    fun clearCalls() {
        jdbc.calls.clear()
        jdbc.scalarResults.clear()
    }

    @Test
    fun `food queries bind absent optional filters as varchar`() {
        repository.searchFoods(userId, null, null, true, 0, 20)
        repository.countFoods(userId, null, null, true)

        assertFoodCalls(
            expectedValues = listOf(true, userId, null, null, null, null, null),
            expectedTypes = listOf(Types.BOOLEAN, Types.OTHER, Types.VARCHAR, Types.VARCHAR, Types.VARCHAR, Types.VARCHAR, Types.VARCHAR),
            offset = 0
        )
    }

    @Test
    fun `food queries bind supplied filters and pagination with declared types`() {
        repository.searchFoods(userId, " Oat ", "ingredient", false, 40, 20)
        repository.countFoods(userId, " Oat ", "ingredient", false)

        assertFoodCalls(
            expectedValues = listOf(false, userId, "ingredient", "ingredient", "%oat%", "%oat%", "%oat%"),
            expectedTypes = listOf(Types.BOOLEAN, Types.OTHER, Types.VARCHAR, Types.VARCHAR, Types.VARCHAR, Types.VARCHAR, Types.VARCHAR),
            offset = 40
        )
    }

    @Test
    fun `meal queries bind absent optional filter as varchar`() {
        repository.listMeals(userId, dateFrom, dateTo, null, 20, 20)
        repository.countMeals(userId, dateFrom, dateTo, null)

        assertMealCalls(
            expectedValues = listOf(userId, dateFrom, dateTo, null, null),
            expectedTypes = listOf(Types.OTHER, Types.DATE, Types.DATE, Types.VARCHAR, Types.VARCHAR)
        )
    }

    @Test
    fun `meal queries bind supplied optional filter and pagination with declared types`() {
        repository.listMeals(userId, dateFrom, dateTo, "lunch", 20, 20)
        repository.countMeals(userId, dateFrom, dateTo, "lunch")

        assertMealCalls(
            expectedValues = listOf(userId, dateFrom, dateTo, "lunch", "lunch"),
            expectedTypes = listOf(Types.OTHER, Types.DATE, Types.DATE, Types.VARCHAR, Types.VARCHAR)
        )
    }

    @Test
    fun `scalar queries request boxed numeric result types`() {
        repository.countFoods(userId, null, null, true)
        repository.countCustomFoods(userId, false)
        repository.countMeals(userId, dateFrom, dateTo, null)
        jdbc.scalarResults.addAll(listOf<Any>(1, 99L))
        repository.recalculateDaily(userId, dateFrom, 100L)

        assertEquals(
            listOf(
                Long::class.javaObjectType,
                Long::class.javaObjectType,
                Long::class.javaObjectType,
                Int::class.javaObjectType,
                Long::class.javaObjectType,
            ),
            jdbc.calls.mapNotNull(RecordedQuery::requiredType),
        )
    }

    private fun assertFoodCalls(expectedValues: List<Any?>, expectedTypes: List<Int>, offset: Int) {
        assertEquals(2, jdbc.calls.size)
        assertContains(jdbc.calls[0].sql, "CAST(? AS VARCHAR)")
        assertContains(jdbc.calls[1].sql, "CAST(? AS VARCHAR)")
        assertEquals(whereClause(jdbc.calls[0].sql), whereClause(jdbc.calls[1].sql))
        assertTypedParameters(jdbc.calls[0], expectedValues + listOf(offset, 20), expectedTypes + listOf(Types.INTEGER, Types.INTEGER))
        assertTypedParameters(jdbc.calls[1], expectedValues, expectedTypes)
    }

    private fun assertMealCalls(expectedValues: List<Any?>, expectedTypes: List<Int>) {
        assertEquals(2, jdbc.calls.size)
        assertContains(jdbc.calls[0].sql, "CAST(? AS VARCHAR)")
        assertContains(jdbc.calls[1].sql, "CAST(? AS VARCHAR)")
        assertEquals(whereClause(jdbc.calls[0].sql), whereClause(jdbc.calls[1].sql))
        assertTypedParameters(jdbc.calls[0], expectedValues + listOf(20, 20), expectedTypes + listOf(Types.INTEGER, Types.INTEGER))
        assertTypedParameters(jdbc.calls[1], expectedValues, expectedTypes)
    }

    private fun assertTypedParameters(call: RecordedQuery, expectedValues: List<Any?>, expectedTypes: List<Int>) {
        val parameters = call.args.map { it as SqlParameterValue }
        assertTrue(call.args.all { it is SqlParameterValue })
        assertEquals(expectedValues, parameters.map(SqlParameterValue::getValue))
        assertEquals(expectedTypes, parameters.map { it.sqlType })
    }

    private fun whereClause(sql: String) = sql.substringAfter(" WHERE ").substringBefore(" ORDER BY ")
}

private data class RecordedQuery(val sql: String, val args: List<Any?>, val requiredType: Class<*>? = null)

private class RecordingJdbcTemplate : JdbcTemplate() {
    val calls = mutableListOf<RecordedQuery>()
    val scalarResults = ArrayDeque<Any>()

    override fun <T : Any?> query(sql: String, rowMapper: RowMapper<T>, vararg args: Any?): List<T> {
        calls += RecordedQuery(sql, args.toList())
        return emptyList()
    }

    @Suppress("UNCHECKED_CAST")
    override fun <T : Any> queryForObject(sql: String, requiredType: Class<T>, vararg args: Any?): T? {
        calls += RecordedQuery(sql, args.toList(), requiredType)
        val value = if (scalarResults.isNotEmpty()) scalarResults.removeFirst() else if (requiredType == Int::class.javaObjectType) 0 else 0L
        return value as T
    }

    override fun update(sql: String, vararg args: Any?): Int = 1
}
