package cn.esuny.healthmind.infrastructure.json

import cn.esuny.healthmind.domain.task.FailureCategory
import cn.esuny.healthmind.domain.task.TaskExecutionException
import com.networknt.schema.SchemaRegistry
import com.networknt.schema.SpecificationVersion
import org.springframework.stereotype.Component
import tools.jackson.databind.JsonNode

@Component
class JsonSchemaService(private val canonicalJson: CanonicalJson) {
    private val registry = SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_2020_12)

    fun validate(schemaJson: String, value: JsonNode) {
        val schema = registry.getSchema(canonicalJson.parse(schemaJson))
        val errors = schema.validate(value)
        if (errors.isNotEmpty()) {
            throw TaskExecutionException(
                code = "OUTPUT_CONTRACT_INVALID",
                category = FailureCategory.CONTRACT,
                message = errors.take(3).joinToString("; ") { it.message },
            )
        }
    }
}
