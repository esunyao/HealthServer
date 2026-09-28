"""JWT bearer verification for HealthMind-to-Agent service calls."""

from __future__ import annotations

import asyncio
from typing import Any

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient

from .runtime_config import RuntimeSettings

_ALGORITHMS = ("RS256", "RS384", "ES256", "ES384")


class TokenVerifier:
    def __init__(self, settings: RuntimeSettings, jwks_client: Any | None = None) -> None:
        self.settings = settings
        self.jwks_client = jwks_client or PyJWKClient(
            settings.oauth_jwks_url,
            cache_keys=True,
            cache_jwk_set=True,
            timeout=5,
        )

    async def verify(self, token: str) -> dict[str, Any]:
        try:
            signing_key = await asyncio.to_thread(self.jwks_client.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(_ALGORITHMS),
                audience=self.settings.oauth_audience,
                issuer=self.settings.oauth_issuer,
                options={"require": ["exp", "iss", "aud"]},
            )
        except Exception as exception:
            raise self._unauthorized() from exception

        caller = claims.get("azp") or claims.get("client_id")
        if caller != self.settings.oauth_client_id:
            raise self._unauthorized()
        scopes = claims.get("scope", claims.get("scp", ""))
        if isinstance(scopes, str):
            granted = set(scopes.split())
        elif isinstance(scopes, list):
            granted = {str(scope) for scope in scopes}
        else:
            granted = set()
        if self.settings.oauth_scope not in granted:
            raise self._unauthorized()
        return claims

    @staticmethod
    def _unauthorized() -> HTTPException:
        return HTTPException(
            status_code=401,
            detail="Invalid service access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
