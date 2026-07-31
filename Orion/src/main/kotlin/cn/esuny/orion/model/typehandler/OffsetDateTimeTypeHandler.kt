package cn.esuny.orion.model.typehandler

import org.apache.ibatis.type.BaseTypeHandler
import org.apache.ibatis.type.JdbcType
import org.apache.ibatis.type.MappedJdbcTypes
import org.apache.ibatis.type.MappedTypes
import java.sql.CallableStatement
import java.sql.PreparedStatement
import java.sql.ResultSet
import java.time.OffsetDateTime

/**
 * java.sql.Timestamp 与 java.time.OffsetDateTime 互转
 *
 * PostgreSQL 的 TIMESTAMP WITH TIME ZONE 类型通过 JDBC 返回 java.sql.Timestamp，
 * 此类型处理器负责将其转换为 Kotlin 的 OffsetDateTime。
 */
@MappedTypes(OffsetDateTime::class)
@MappedJdbcTypes(JdbcType.TIMESTAMP)
class OffsetDateTimeTypeHandler : BaseTypeHandler<OffsetDateTime>() {

    override fun setNonNullParameter(ps: PreparedStatement, i: Int, parameter: OffsetDateTime, jdbcType: JdbcType?) {
        ps.setObject(i, parameter)
    }

    override fun getNullableResult(rs: ResultSet, columnName: String): OffsetDateTime? {
        return rs.getObject(columnName, OffsetDateTime::class.java)
    }

    override fun getNullableResult(rs: ResultSet, columnIndex: Int): OffsetDateTime? {
        return rs.getObject(columnIndex, OffsetDateTime::class.java)
    }

    override fun getNullableResult(cs: CallableStatement, columnIndex: Int): OffsetDateTime? {
        return cs.getObject(columnIndex, OffsetDateTime::class.java)
    }
}
