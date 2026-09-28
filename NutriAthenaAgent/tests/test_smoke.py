from __future__ import annotations

import asyncio
import json
from uuid import UUID

import httpx

from nutriathena_agent import smoke
from nutriathena_agent.runtime_config import RuntimeSettings


def test_smoke_uses_release_uuid_and_never_prints_response_details(monkeypatch):
    task_id = "11111111-1111-4111-8111-111111111111"
    attempt_id = "22222222-2222-4222-8222-222222222222"
    release_id = UUID("33333333-3333-4333-8333-333333333333")
    settings = RuntimeSettings(
        host="127.0.0.1",
        port=8101,
        database_url="unused",
        oauth_issuer="https://issuer.test",
        oauth_jwks_url="https://issuer.test/jwks",
        oauth_audience="aud",
        oauth_client_id="healthmind-client",
        oauth_scope="healthmind.agent.run",
        release_id=release_id,
        deployment_key="local-route-key",
        assistant_id="assistant-test",
    )
    monkeypatch.setattr(smoke, "load_env", lambda: None)
    monkeypatch.setattr(smoke, "load_runtime_settings", lambda: settings)
    monkeypatch.setattr(smoke, "compute_artifact_sha256", lambda: "a" * 64)
    monkeypatch.setenv("NUTRIATHENA_SMOKE_BASE_URL", "https://agent.test")
    monkeypatch.setenv("NUTRIATHENA_SMOKE_TOKEN_URL", "https://issuer.test/token")
    monkeypatch.setenv("NUTRIATHENA_SMOKE_CLIENT_ID", "smoke-client")
    monkeypatch.setenv("NUTRIATHENA_SMOKE_CLIENT_SECRET", "do-not-return-this")

    requests: list[httpx.Request] = []
    run_posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal run_posts
        requests.append(request)
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "private-token"})
        if request.url.path == "/threads":
            return httpx.Response(200, json={"thread_id": attempt_id})
        if request.url.path == f"/threads/{attempt_id}/runs":
            run_posts += 1
            body = json.loads(request.content)
            assert body["metadata"]["release_id"] == str(release_id)
            assert body["metadata"]["artifact_sha256"] == "a" * 64
            assert request.headers["Idempotency-Key"] == attempt_id
            return httpx.Response(
                200,
                json={
                    "run_id": "44444444-4444-4444-8444-444444444444",
                    "status": "success",
                    "assistant_id": "assistant-test",
                    "metadata": {"artifact_sha256": "a" * 64},
                },
            )
        if request.url.path.endswith("/wait"):
            return httpx.Response(
                200,
                json={"output": {"overall_confidence": 0.8, "items": [{"name": "private-food"}]}},
            )
        raise AssertionError(f"unexpected request path: {request.url.path}")

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    summary = asyncio.run(smoke.run_smoke(task_id=task_id, attempt_id=attempt_id, trace_id="test-trace"))

    assert run_posts == 1
    assert summary == {
        "run_id": "44444444-4444-4444-8444-444444444444",
        "status": "success",
        "assistant_id": "assistant-test",
        "artifact_sha256": "a" * 64,
        "output_status": "analysis",
        "item_count": 1,
    }
    assert "private-token" not in json.dumps(summary)
    assert "private-food" not in json.dumps(summary)
    assert "do-not-return-this" not in json.dumps(summary)
    assert all(request.headers.get("Authorization", "") != "Bearer do-not-return-this" for request in requests)
