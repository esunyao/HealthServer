package cn.esuny.nutrimemo.persistence

import org.apache.ibatis.type.BaseTypeHandler
import org.apache.ibatis.type.JdbcType
import org.apache.ibatis.type.MappedJdbcTypes
import org.apache.ibatis.type.MappedTypes
import java.sql.CallableStatement
import java.sql.PreparedStatement
import java.sql.ResultSet
import java.sql.Types
import java.util.UUID

@MappedTypes(UUID::class)
@MappedJdbcTypes(value = [JdbcType.OTHER], includeNullJdbcType = true)
class PgUuidTypeHandler : BaseTypeHandler<UUID>() {
    override fun setNonNullParameter(ps: PreparedStatement, i: Int, parameter: UUID, jdbcType: JdbcType?) = ps.setObject(i, parameter, Types.OTHER)
    override fun getNullableResult(rs: ResultSet, columnName: String): UUID? = uuid(rs.getObject(columnName))
    override fun getNullableResult(rs: ResultSet, columnIndex: Int): UUID? = uuid(rs.getObject(columnIndex))
    override fun getNullableResult(cs: CallableStatement, columnIndex: Int): UUID? = uuid(cs.getObject(columnIndex))
    private fun uuid(value: Any?): UUID? = value?.let { if (it is UUID) it else UUID.fromString(it.toString()) }
}
