package cn.esuny.healthmind.infrastructure.json

import cn.esuny.healthmind.domain.task.TaskExecutionException
import kotlin.test.Test
import kotlin.test.assertFailsWith
import tools.jackson.databind.ObjectMapper

class JsonSchemaServiceTest {
    private val canonical = CanonicalJson(ObjectMapper())
    private val schemas = JsonSchemaService(canonical)
    private val schema = """{"type":"object","required":["value"],"properties":{"value":{"type":"number"}}}"""

    @Test
    fun `accepts valid structured output`() {
        schemas.validate(schema, canonical.parse("""{"value":1}"""))
    }

    @Test
    fun `rejects output contract violation`() {
        assertFailsWith<TaskExecutionException> {
            schemas.validate(schema, canonical.parse("""{"value":"wrong"}"""))
        }
    }
}
