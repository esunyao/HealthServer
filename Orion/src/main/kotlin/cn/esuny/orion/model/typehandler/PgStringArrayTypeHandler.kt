package cn.esuny.orion.model.typehandler

import org.apache.ibatis.type.BaseTypeHandler
import org.apache.ibatis.type.JdbcType
import org.apache.ibatis.type.MappedJdbcTypes
import org.apache.ibatis.type.MappedTypes
import org.postgresql.util.PGobject
import java.sql.CallableStatement
import java.sql.PreparedStatement
import java.sql.ResultSet

/**
 * PostgreSQL TEXT[] 与 Kotlin List<String> 互转
 * 存入时用逗号拼接为 PostgreSQL 数组字面量，读出时按逗号拆分
 */
@MappedTypes(List::class)
@MappedJdbcTypes(JdbcType.ARRAY)
class PgStringArrayTypeHandler : BaseTypeHandler<List<String>>() {

    override fun setNonNullParameter(ps: PreparedStatement, i: Int, parameter: List<String>, jdbcType: JdbcType?) {
        val array = ps.connection.createArrayOf("text", parameter.toTypedArray())
        ps.setArray(i, array)
    }

    override fun getNullableResult(rs: ResultSet, columnName: String): List<String>? {
        val array = rs.getArray(columnName) ?: return null
        return (array.array as? Array<*>)?.filterIsInstance<String>() ?: emptyList()
    }

    override fun getNullableResult(rs: ResultSet, columnIndex: Int): List<String>? {
        val array = rs.getArray(columnIndex) ?: return null
        return (array.array as? Array<*>)?.filterIsInstance<String>() ?: emptyList()
    }

    override fun getNullableResult(cs: CallableStatement, columnIndex: Int): List<String>? {
        val array = cs.getArray(columnIndex) ?: return null
        return (array.array as? Array<*>)?.filterIsInstance<String>() ?: emptyList()
    }
}
