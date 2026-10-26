package cn.esuny.contracts.agent.v1

import com.fasterxml.jackson.databind.ObjectMapper
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AgentProtocolFixturesTest {
    private val mapper = ObjectMapper()

    @Test
    fun `thread and run fixtures share one identity tuple`() {
        val threadRequest = fixture("examples/thread-create-request.json")
        val threadResponse = fixture("examples/thread-response.json")
        val runRequest = fixture("examples/run-create-request.json")
        val runResponse = fixture("examples/run-response.json")

        assertEquals(threadRequest.path("thread_id"), threadResponse.path("thread_id"))
        assertEquals(threadRequest.path("metadata"), threadResponse.path("metadata"))
        assertEquals(threadRequest.path("metadata").path("task_id"), runRequest.path("input").path("task_id"))
        assertEquals(threadRequest.path("metadata").path("attempt_id"), runRequest.path("input").path("attempt_id"))
        assertEquals(threadResponse.path("thread_id"), runResponse.path("thread_id"))
        assertEquals(threadResponse.path("metadata").path("task_id"), runResponse.path("task_id"))
        assertEquals(threadResponse.path("metadata").path("attempt_id"), runResponse.path("attempt_id"))
        assertEquals(runRequest.path("metadata"), runResponse.path("metadata"))
    }

    @Test
    fun `schemas reject undeclared response fields`() {
        val schemas = listOf(
            "thread-create-request.schema.json",
            "thread-response.schema.json",
            "run-create-request.schema.json",
            "run-response.schema.json",
        )

        schemas.forEach { name ->
            val schema = fixture(name)
            assertEquals("https://json-schema.org/draft/2020-12/schema", schema.path("\$schema").asText())
            assertTrue(schema.path("\$id").asText().startsWith("https://healthmind.local/schema/agent-protocol/v1/"))
            assertFalse(schema.path("additionalProperties").asBoolean())
        }
    }

    private fun fixture(name: String) = checkNotNull(javaClass.getResourceAsStream("/agent-protocol/v1/$name")).use {
        mapper.readTree(it)
    }
}
