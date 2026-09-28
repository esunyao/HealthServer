"""Safe authenticated smoke against a deployed HealthMind-compatible Agent."""

from __future__ import annotations

import asyncio
import os
import time
from uuid import UUID

import httpx

from .artifact import compute_artifact_sha256
from .config import load_env
from .runtime_config import load_runtime_settings


async def run_smoke(*, task_id: str, attempt_id: str, trace_id: str) -> dict[str, object]:
    """Submit once, reconcile ambiguous transport results, and print no meal data."""
    load_env()
    settings = load_runtime_settings()
    task = str(UUID(task_id))
    attempt = str(UUID(attempt_id))
    base_url = os.environ.get("NUTRIATHENA_SMOKE_BASE_URL", f"http://127.0.0.1:{settings.port}").rstrip("/")
    token_url = os.environ.get("NUTRIATHENA_SMOKE_TOKEN_URL", "").strip()
    client_id = os.environ.get("NUTRIATHENA_SMOKE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NUTRIATHENA_SMOKE_CLIENT_SECRET", "")
    scope = os.environ.get("NUTRIATHENA_SMOKE_SCOPE", settings.oauth_scope)
    missing = [
        name
        for name, value in (
            ("NUTRIATHENA_SMOKE_TOKEN_URL", token_url),
            ("NUTRIATHENA_SMOKE_CLIENT_ID", client_id),
            ("NUTRIATHENA_SMOKE_CLIENT_SECRET", client_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"缺少真实 smoke 配置：{'、'.join(missing)}")

    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        token_response = await client.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": scope,
            },
        )
        if not token_response.is_success:
            raise RuntimeError(f"Smoke OAuth 请求失败，HTTP {token_response.status_code}")
        access_token = token_response.json().get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("Smoke OAuth 响应缺少 access_token")
        headers = {"Authorization": f"Bearer {access_token}"}
        thread_response = await client.post(
            f"{base_url}/threads",
            headers=headers,
            json={"thread_id": attempt, "metadata": {"task_id": task, "attempt_id": attempt}},
        )
        if not thread_response.is_success:
            raise RuntimeError(f"Agent 创建或复用 thread 失败，HTTP {thread_response.status_code}")

        body = {
            "assistant_id": settings.assistant_id,
            "input": {"task_id": task, "attempt_id": attempt, "trace_id": trace_id},
            "metadata": {
                "task_id": task,
                "attempt_id": attempt,
                "release_id": str(settings.release_id),
                "artifact_sha256": compute_artifact_sha256(),
            },
            "on_completion": "keep",
        }
        try:
            response = await client.post(
                f"{base_url}/threads/{attempt}/runs",
                headers={**headers, "Idempotency-Key": attempt},
                json=body,
            )
        except httpx.HTTPError:
            # Never issue a second POST after an ambiguous run submission. The
            # list endpoint is the reconciliation source for attempt_id.
            response = None

        if response is None:
            listed = await client.get(f"{base_url}/threads/{attempt}/runs", headers=headers)
            if not listed.is_success:
                raise RuntimeError("Run 提交结果不确定，且无法通过 list runs 对账")
            rows = listed.json()
            matching = [row for row in rows if row.get("attempt_id") == attempt]
            if len(matching) != 1:
                raise RuntimeError("Run 提交结果不确定；没有唯一可对账记录，请勿重复创建新 attempt")
            run = matching[0]
        else:
            if not response.is_success:
                raise RuntimeError(f"Agent 创建或复用 run 失败，HTTP {response.status_code}")
            run = response.json()

        run_id = run.get("run_id")
        if not isinstance(run_id, str):
            raise RuntimeError("Agent 响应缺少 run_id")
        deadline = time.monotonic() + int(os.environ.get("NUTRIATHENA_SMOKE_TIMEOUT_SECONDS", "660"))
        status = run.get("status", "pending")
        while status in {"pending", "running"} and time.monotonic() < deadline:
            await asyncio.sleep(2)
            status_response = await client.get(f"{base_url}/runs/{run_id}", headers=headers)
            if not status_response.is_success:
                raise RuntimeError(f"Agent 状态查询失败，HTTP {status_response.status_code}")
            run = status_response.json()
            status = run.get("status")
        summary: dict[str, object] = {
            "run_id": run_id,
            "status": status,
            "assistant_id": run.get("assistant_id"),
            "artifact_sha256": run.get("metadata", {}).get("artifact_sha256"),
        }
        if status == "success":
            result_response = await client.get(f"{base_url}/runs/{run_id}/wait?timeout_seconds=1", headers=headers)
            if not result_response.is_success:
                raise RuntimeError(f"Agent 结果读取失败，HTTP {result_response.status_code}")
            output = result_response.json().get("output")
            summary["output_status"] = output.get("status", "analysis") if isinstance(output, dict) else "invalid"
            summary["item_count"] = len(output.get("items", [])) if isinstance(output, dict) and isinstance(output.get("items"), list) else 0
        elif status in {"error", "interrupted"}:
            summary["error_code"] = run.get("error_code")
        else:
            summary["status"] = "still_running"
        return summary
