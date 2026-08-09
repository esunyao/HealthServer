package cn.esuny.orion.config

import cn.esuny.orion.mapper.FileCleanupTaskMapper
import cn.esuny.orion.mapper.UserMapper
import cn.esuny.orion.mapper.UserProfileMapper
import cn.esuny.orion.model.entity.user.User
import cn.esuny.orion.model.typehandler.PgUuidTypeHandler
import com.baomidou.mybatisplus.core.MybatisConfiguration
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.apache.ibatis.type.JdbcType
import org.junit.jupiter.api.Test
import java.sql.PreparedStatement
import java.sql.ResultSet
import java.sql.Types
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class UuidTypeHandlerTest {

    @Test
    fun `registers UUID handler and parses custom mappers`() {
        val configuration = MybatisConfiguration()
        MyBatisPlusConfig().uuidTypeHandlerCustomizer().customize(configuration)

        assertIs<PgUuidTypeHandler>(configuration.typeHandlerRegistry.getTypeHandler(UUID::class.java))
        assertIs<PgUuidTypeHandler>(configuration.typeHandlerRegistry.getTypeHandler(UUID::class.java, JdbcType.OTHER))

        configuration.addMapper(UserMapper::class.java)
        configuration.addMapper(UserProfileMapper::class.java)
        configuration.addMapper(FileCleanupTaskMapper::class.java)

        val user = User(userId = UUID.randomUUID(), username = "test", email = "test@example.com")
        val parameters = configuration
            .getMappedStatement("${UserMapper::class.java.name}.upsertIdentity")
            .getBoundSql(user)
            .parameterMappings

        assertTrue(parameters.any { it.property == "userId" && it.typeHandler is PgUuidTypeHandler })
    }

    @Test
    fun `binds and reads PostgreSQL UUID values`() {
        val handler = PgUuidTypeHandler()
        val userId = UUID.randomUUID()
        val statement = mockk<PreparedStatement>(relaxed = true)
        val resultSet = mockk<ResultSet>()
        every { resultSet.getObject("user_id") } returns userId

        handler.setNonNullParameter(statement, 1, userId, JdbcType.OTHER)

        verify { statement.setObject(1, userId, Types.OTHER) }
        assertEquals(userId, handler.getNullableResult(resultSet, "user_id"))
    }
}
