package cn.esuny.gateway.security

import org.springframework.security.oauth2.core.OAuth2Error
import org.springframework.security.oauth2.core.OAuth2TokenValidator
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult
import org.springframework.security.oauth2.jwt.Jwt

/** 验证 Access Token 的 aud 声明，避免其他 OIDC 客户端的 Token 调用本 API。 */
class AudienceValidator(private val requiredAudiences: Set<String>) : OAuth2TokenValidator<Jwt> {

    override fun validate(token: Jwt): OAuth2TokenValidatorResult {
        if (token.audience?.any(requiredAudiences::contains) == true) {
            return OAuth2TokenValidatorResult.success()
        }

        val error = OAuth2Error(
            "invalid_token",
            "The token audience is not allowed for this gateway.",
            null
        )
        return OAuth2TokenValidatorResult.failure(error)
    }
}
