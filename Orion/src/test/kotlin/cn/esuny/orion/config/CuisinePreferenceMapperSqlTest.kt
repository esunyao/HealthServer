package cn.esuny.orion.config

import cn.esuny.orion.mapper.UserCuisinePreferenceMapper
import cn.esuny.orion.model.typehandler.PgUuidTypeHandler
import com.baomidou.mybatisplus.core.MybatisConfiguration
import org.junit.jupiter.api.Test
import java.util.UUID
import kotlin.test.assertContains
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CuisinePreferenceMapperSqlTest {

    @Test
    fun `delete by user does not append query wrapper ordering`() {
        val configuration = MybatisConfiguration()
        MyBatisPlusConfig().uuidTypeHandlerCustomizer().customize(configuration)
        configuration.addMapper(UserCuisinePreferenceMapper::class.java)

        val boundSql = configuration
            .getMappedStatement("${UserCuisinePreferenceMapper::class.java.name}.deleteByUserId")
            .getBoundSql(mapOf("userId" to UUID.randomUUID()))

        assertContains(boundSql.sql, "DELETE FROM orion.user_cuisine_preferences")
        assertFalse(boundSql.sql.contains("ORDER BY"))
        assertTrue(boundSql.parameterMappings.any { it.property == "userId" && it.typeHandler is PgUuidTypeHandler })
    }
}
