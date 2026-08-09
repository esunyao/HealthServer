package cn.esuny.orion.model.typehandler

import org.apache.ibatis.type.BaseTypeHandler
import org.apache.ibatis.type.JdbcType
import org.apache.ibatis.type.MappedJdbcTypes
import org.apache.ibatis.type.MappedTypes
import java.sql.CallableStatement
import java.sql.PreparedStatement
import java.sql.ResultSet
import java.sql.Types
import java.util.UUID

/** PostgreSQL uuid 与 Kotlin UUID 的显式映射。 */
@MappedTypes(UUID::class)
@MappedJdbcTypes(value = [JdbcType.OTHER], includeNullJdbcType = true)
class PgUuidTypeHandler : BaseTypeHandler<UUID>() {

    override fun setNonNullParameter(ps: PreparedStatement, i: Int, parameter: UUID, jdbcType: JdbcType?) {
        ps.setObject(i, parameter, Types.OTHER)
    }

    override fun getNullableResult(rs: ResultSet, columnName: String): UUID? = toUuid(rs.getObject(columnName))

    override fun getNullableResult(rs: ResultSet, columnIndex: Int): UUID? = toUuid(rs.getObject(columnIndex))

    override fun getNullableResult(cs: CallableStatement, columnIndex: Int): UUID? = toUuid(cs.getObject(columnIndex))

    private fun toUuid(value: Any?): UUID? = when (value) {
        null -> null
        is UUID -> value
        else -> UUID.fromString(value.toString())
    }
}
