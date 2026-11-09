from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from nutriathena_agent.integrations.auth import TokenVerifier
from nutriathena_agent.config import RuntimeSettings

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _settings() -> RuntimeSettings:
    return RuntimeSettings(
        host="127.0.0.1",
        port=8101,
        database_url="postgresql://unused",
        oauth_issuer="https://issuer.example.test",
        oauth_jwks_url="https://issuer.example.test/jwks",
        oauth_audience="healthmind-agent",
        oauth_client_id="healthmind-client",
        oauth_scope="healthmind.agent.run",
        release_id=UUID("33333333-3333-4333-8333-333333333333"),
        deployment_key="deployment-test",
        assistant_id="assistant-test",
    )


class FakeJwksClient:
    def get_signing_key_from_jwt(self, token: str):
        return SimpleNamespace(key=_PRIVATE_KEY.public_key())


def _token(**overrides: object) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": "https://issuer.example.test",
        "aud": "healthmind-agent",
        "azp": "healthmind-client",
        "scope": "healthmind.agent.run",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256", headers={"kid": "test-key"})


def test_token_verifier_checks_signature_issuer_audience_caller_and_scope():
    verifier = TokenVerifier(_settings(), FakeJwksClient())
    claims = asyncio.run(verifier.verify(_token()))
    assert claims["iss"] == "https://issuer.example.test"
    assert claims["azp"] == "healthmind-client"


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://wrong.example.test"},
        {"aud": "another-audience"},
        {"azp": "not-healthmind"},
        {"scope": "healthmind.other.scope"},
        {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    ],
)
def test_token_verifier_rejects_wrong_claims_without_echoing_token(overrides):
    verifier = TokenVerifier(_settings(), FakeJwksClient())
    token = _token(**overrides)
    with pytest.raises(HTTPException) as exception:
        asyncio.run(verifier.verify(token))
    assert exception.value.status_code == 401
    assert exception.value.headers == {"WWW-Authenticate": "Bearer"}
    assert token not in str(exception.value.detail)


@pytest.mark.parametrize(
    "overrides",
    [
        {"azp": None, "client_id": "healthmind-client"},
        {"scope": "other.read healthmind.agent.run"},
        {"scope": ["other.read", "healthmind.agent.run"]},
    ],
)
def test_token_verifier_accepts_supported_caller_and_scope_forms(overrides):
    claims = asyncio.run(TokenVerifier(_settings(), FakeJwksClient()).verify(_token(**overrides)))
    assert claims["aud"] == "healthmind-agent"


def test_token_verifier_accepts_scp_list_when_scope_is_absent():
    claims = jwt.decode(_token(), options={"verify_signature": False})
    del claims["scope"]
    claims["scp"] = ["healthmind.agent.run"]
    token = jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256")
    assert asyncio.run(TokenVerifier(_settings(), FakeJwksClient()).verify(token))["scp"] == ["healthmind.agent.run"]


@pytest.mark.parametrize("scope", [None, 5, {}, "healthmind.agent.run.extra", ["healthmind.other"]])
def test_token_verifier_requires_exact_scope(scope):
    with pytest.raises(HTTPException) as caught:
        asyncio.run(TokenVerifier(_settings(), FakeJwksClient()).verify(_token(scope=scope)))
    assert caught.value.status_code == 401


@pytest.mark.parametrize("required", ["exp", "iss", "aud"])
def test_token_verifier_rejects_missing_required_claims(required):
    claims = jwt.decode(_token(), options={"verify_signature": False})
    del claims[required]
    token = jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(TokenVerifier(_settings(), FakeJwksClient()).verify(token))
    assert caught.value.status_code == 401
    assert isinstance(caught.value.__cause__, jwt.MissingRequiredClaimError)


def test_token_verifier_rejects_a_signature_from_another_key():
    claims = jwt.decode(_token(), options={"verify_signature": False})
    another_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(claims, another_key, algorithm="RS256")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(TokenVerifier(_settings(), FakeJwksClient()).verify(token))
    assert isinstance(caught.value.__cause__, jwt.InvalidSignatureError)


def test_token_verifier_rejects_unapproved_signing_algorithm():
    claims = jwt.decode(_token(), options={"verify_signature": False})
    token = jwt.encode(claims, "synthetic-symmetric-signing-key-32-bytes", algorithm="HS256")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(TokenVerifier(_settings(), FakeJwksClient()).verify(token))
    assert caught.value.status_code == 401
    assert isinstance(caught.value.__cause__, jwt.InvalidAlgorithmError)


def test_jwks_lookup_failure_preserves_cause_without_exposing_token():
    root_cause = OSError("offline JWKS unavailable")

    class FailingJwks:
        def get_signing_key_from_jwt(self, token):
            raise root_cause

    token = _token()
    with pytest.raises(HTTPException) as caught:
        asyncio.run(TokenVerifier(_settings(), FailingJwks()).verify(token))
    assert caught.value.__cause__ is root_cause
    assert caught.value.headers == {"WWW-Authenticate": "Bearer"}
    assert token not in str(caught.value.detail)
