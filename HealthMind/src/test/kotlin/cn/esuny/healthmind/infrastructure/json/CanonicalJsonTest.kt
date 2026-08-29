package cn.esuny.healthmind.infrastructure.json

import kotlin.test.Test
import kotlin.test.assertEquals
import tools.jackson.databind.ObjectMapper

class CanonicalJsonTest {
    private val canonical = CanonicalJson(ObjectMapper())

    @Test
    fun `object property order does not change digest`() {
        val first = canonical.parse("""{"b":2,"a":{"d":4,"c":3}}""")
        val second = canonical.parse("""{"a":{"c":3,"d":4},"b":2}""")
        assertEquals(canonical.sha256(first), canonical.sha256(second))
    }
}
