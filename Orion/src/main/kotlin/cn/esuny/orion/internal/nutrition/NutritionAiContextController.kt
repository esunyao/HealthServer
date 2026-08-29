package cn.esuny.orion.internal.nutrition

import jakarta.validation.Valid
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/internal/v1/ai-context")
class NutritionAiContextController(
    private val service: NutritionAiContextService,
    private val security: OrionInternalSecurityProperties,
) {
    @PostMapping("/nutrition")
    fun getNutritionContext(
        @Valid @RequestBody request: NutritionAiContextRequest,
        authentication: JwtAuthenticationToken,
    ): NutritionAiContextResponse {
        val caller = authentication.token.getClaimAsString("azp")
            ?: authentication.token.getClaimAsString("client_id")
        require(caller == security.allowedHealthMindClientId) { "Internal caller is not HealthMind" }
        return service.get(request)
    }
}
