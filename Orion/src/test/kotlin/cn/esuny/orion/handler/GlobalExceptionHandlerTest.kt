package cn.esuny.orion.handler

import org.junit.jupiter.api.Test
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.dao.DuplicateKeyException
import org.springframework.http.HttpStatus
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

class GlobalExceptionHandlerTest {

    private val handler = GlobalExceptionHandler()

    @Test
    fun `duplicate active goal is reported as conflict`() {
        val response = handler.handleDuplicateKey(
            DuplicateKeyException("duplicate key violates constraint uq_health_goals_active_type")
        )

        assertEquals(HttpStatus.CONFLICT, response.statusCode)
        assertNotNull(response.body)
        assertEquals(409, response.body!!.code)
        assertEquals("该类型的有效健康目标已存在", response.body!!.message)
    }

    @Test
    fun `database check constraint is reported as bad request`() {
        val response = handler.handleDataIntegrityViolation(
            DataIntegrityViolationException("violates user_dietary_restrictions_category_check")
        )

        assertEquals(HttpStatus.BAD_REQUEST, response.statusCode)
        assertNotNull(response.body)
        assertEquals(400, response.body!!.code)
    }
}
