package cn.esuny.orion.model.typehandler

import org.apache.ibatis.type.BaseTypeHandler
import org.apache.ibatis.type.JdbcType
import org.postgresql.util.PGobject
import java.sql.CallableStatement
import java.sql.PreparedStatement
import java.sql.ResultSet

class PgJsonbTypeHandler : BaseTypeHandler<String>() {
    override fun setNonNullParameter(ps: PreparedStatement, i: Int, parameter: String, jdbcType: JdbcType?) {
        ps.setObject(i, PGobject().apply { type = "jsonb"; value = parameter })
    }

    override fun getNullableResult(rs: ResultSet, columnName: String): String? = rs.getObject(columnName)?.toString()
    override fun getNullableResult(rs: ResultSet, columnIndex: Int): String? = rs.getObject(columnIndex)?.toString()
    override fun getNullableResult(cs: CallableStatement, columnIndex: Int): String? = cs.getObject(columnIndex)?.toString()
}
