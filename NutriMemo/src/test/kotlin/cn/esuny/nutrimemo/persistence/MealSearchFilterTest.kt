package cn.esuny.nutrimemo.persistence

import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.MethodSource
import java.time.LocalDate
import java.util.UUID
import java.util.stream.Stream
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class MealSearchFilterTest {
    @ParameterizedTest
    @MethodSource("filters")
    fun `builds only typed parameters for each optional filter combination`(type: String?, keyword: String?, expectedParameterCount: Int) {
        val filter = mealSearchFilter(UUID.randomUUID(), LocalDate.parse("2026-08-01"), LocalDate.parse("2026-08-07"), type, keyword)

        assertFalse(filter.whereClause.contains("? IS NULL"))
        // parameters 是 List<Any>，构造器不允许把未声明类型的 null 传给 JDBC。
        assertEquals(expectedParameterCount, filter.parameters.size)
        assertEquals(type != null, filter.whereClause.contains("m.meal_type=?"))
        assertEquals(keyword != null, filter.whereClause.contains("m.notes ILIKE ?"))
        if (keyword != null) assertTrue(filter.parameters.takeLast(2).all { it == keyword })
    }

    companion object {
        @JvmStatic
        fun filters(): Stream<org.junit.jupiter.params.provider.Arguments> = Stream.of(
            org.junit.jupiter.params.provider.Arguments.of(null, null, 3),
            org.junit.jupiter.params.provider.Arguments.of("lunch", null, 4),
            org.junit.jupiter.params.provider.Arguments.of(null, "%鸡胸%", 5),
            org.junit.jupiter.params.provider.Arguments.of("dinner", "%鸡胸%", 6),
        )
    }
}
