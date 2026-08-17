package cn.esuny.nutrimemo.handler

import org.junit.jupiter.api.Test
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.http.HttpStatus
import java.sql.SQLException
import kotlin.test.assertEquals

class GlobalExceptionHandlerTest {
    private val handler = GlobalExceptionHandler()

    @Test
    fun `constraint SQL state returns a bad request`() {
        val response = handler.integrity(errorWithSqlState("23514"))

        assertEquals(HttpStatus.BAD_REQUEST, response.statusCode)
        assertEquals(400, response.body?.code)
        assertEquals("请求数据违反业务约束", response.body?.message)
    }

    @Test
    fun `driver mapping SQL state returns an internal server error`() {
        val response = handler.integrity(errorWithSqlState("22023"))

        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, response.statusCode)
        assertEquals(500, response.body?.code)
        assertEquals("服务器内部错误，请联系管理员", response.body?.message)
    }

    private fun errorWithSqlState(sqlState: String) =
        DataIntegrityViolationException("database failure", SQLException("database failure", sqlState))
}
