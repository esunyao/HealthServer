package cn.esuny.nutrimemo.integration

import kotlin.test.Test
import kotlin.test.assertEquals

class AiWritebackPolicyTest {
    @Test
    fun `manual data wins over ai`() {
        assertEquals(AiWritebackDecision.PRESERVE_MANUAL, AiWritebackPolicy.decide("active", true))
    }

    @Test
    fun `deleted meal ignores ai`() {
        assertEquals(AiWritebackDecision.IGNORE_DELETED, AiWritebackPolicy.decide("deleted", false))
    }

    @Test
    fun `unmodified active meal accepts ai`() {
        assertEquals(AiWritebackDecision.APPLY_AI, AiWritebackPolicy.decide("active", false))
    }
}
