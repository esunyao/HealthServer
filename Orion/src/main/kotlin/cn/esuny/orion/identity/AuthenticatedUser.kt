package cn.esuny.orion.identity

import java.util.UUID

data class AuthenticatedUser(
    val userId: UUID,
    val username: String,
    val email: String?,
    val emailVerified: Boolean,
    val displayName: String
)
