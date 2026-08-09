package cn.esuny.orion.service

import cn.esuny.orion.handler.BusinessException
import cn.esuny.orion.identity.AuthenticatedUser
import cn.esuny.orion.mapper.UserMapper
import cn.esuny.orion.model.entity.user.BusinessStatus
import cn.esuny.orion.model.entity.user.User
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import java.util.UUID
import kotlin.test.assertEquals

class IdentityProvisioningServiceTest {
    private val mapper = mockk<UserMapper>(relaxed = true)
    private val service = IdentityProvisioningService(mapper)
    private val id = UUID.fromString("d290f1ee-6c54-4b01-90e6-d701748f0851")

    @Test
    fun `verified Authentik user is upserted with a profile`() {
        every { mapper.selectById(id) } returns user()

        val provisioned = service.provision(identity())

        assertEquals(id, provisioned.userId)
        verify(exactly = 1) { mapper.upsertIdentity(match { it.userId == id && it.emailVerified }) }
        verify(exactly = 1) { mapper.ensureProfile(id) }
    }

    @Test
    fun `unverified identity is rejected before it reaches persistence`() {
        val exception = assertThrows<BusinessException> { service.provision(identity(emailVerified = false)) }

        assertEquals(403, exception.code)
        verify(exactly = 0) { mapper.upsertIdentity(any()) }
    }

    @Test
    fun `deactivated business user cannot be restored by identity sync`() {
        every { mapper.selectById(id) } returns user(status = BusinessStatus.deactivated)

        val exception = assertThrows<BusinessException> { service.provision(identity()) }

        assertEquals(403, exception.code)
        verify(exactly = 1) { mapper.upsertIdentity(any()) }
    }

    private fun identity(emailVerified: Boolean = true) = AuthenticatedUser(id, "test", "test@example.com", emailVerified, "Test")

    private fun user(status: BusinessStatus = BusinessStatus.active) = User(
        userId = id,
        username = "test",
        email = "test@example.com",
        emailVerified = true,
        displayName = "Test",
        businessStatus = status
    )
}
