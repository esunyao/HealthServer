"""Runtime configuration kept separate from the two teaching examples."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from uuid import UUID

from .config import load_env


@dataclass(frozen=True)
class RuntimeSettings:
    host: str
    port: int
    database_url: str = field(repr=False)
    oauth_issuer: str
    oauth_jwks_url: str
    oauth_audience: str
    oauth_client_id: str
    oauth_scope: str
    release_id: UUID
    deployment_key: str
    assistant_id: str
    worker_poll_seconds: float = 0.5
    lease_seconds: int = 90
    run_timeout_seconds: int = 600
    result_retention_hours: int = 24
    row_retention_days: int = 180


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少运行配置：{name}")
    return value


def _integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exception:
        raise RuntimeError(f"运行配置 {name} 必须是整数") from exception
    if not minimum <= value <= maximum:
        raise RuntimeError(f"运行配置 {name} 超出允许范围")
    return value


def load_runtime_settings() -> RuntimeSettings:
    load_env()
    try:
        port = _integer("NUTRIATHENA_PORT", 8101, minimum=1, maximum=65535)
        lease_seconds = _integer("NUTRIATHENA_LEASE_SECONDS", 90, minimum=10, maximum=3600)
        timeout = _integer("NUTRIATHENA_RUN_TIMEOUT_SECONDS", 600, minimum=5, maximum=7200)
        result_retention = _integer("NUTRIATHENA_RESULT_RETENTION_HOURS", 24, minimum=24, maximum=720)
        row_retention = _integer("NUTRIATHENA_ROW_RETENTION_DAYS", 180, minimum=180, maximum=3650)
        poll = float(os.environ.get("NUTRIATHENA_WORKER_POLL_SECONDS", "0.5"))
    except ValueError as exception:
        raise RuntimeError("运行配置 NUTRIATHENA_WORKER_POLL_SECONDS 必须是数字") from exception
    if not 0.05 <= poll <= 30:
        raise RuntimeError("运行配置 NUTRIATHENA_WORKER_POLL_SECONDS 超出允许范围")

    try:
        release_id = UUID(_required("NUTRIATHENA_RELEASE_ID"))
    except ValueError as exception:
        raise RuntimeError("运行配置 NUTRIATHENA_RELEASE_ID 必须是 UUID") from exception

    return RuntimeSettings(
        host=os.environ.get("NUTRIATHENA_HOST", "0.0.0.0"),
        port=port,
        database_url=_required("NUTRIATHENA_DATABASE_URL"),
        oauth_issuer=_required("NUTRIATHENA_OAUTH_ISSUER"),
        oauth_jwks_url=_required("NUTRIATHENA_OAUTH_JWKS_URL"),
        oauth_audience=os.environ.get("NUTRIATHENA_OAUTH_AUDIENCE", "healthmind-agent"),
        oauth_client_id=os.environ.get("NUTRIATHENA_OAUTH_CLIENT_ID", "healthmind-agent"),
        oauth_scope=os.environ.get("NUTRIATHENA_OAUTH_SCOPE", "healthmind.agent.run"),
        release_id=release_id,
        deployment_key=_required("NUTRIATHENA_DEPLOYMENT_KEY"),
        assistant_id=_required("NUTRIATHENA_ASSISTANT_ID"),
        worker_poll_seconds=poll,
        lease_seconds=lease_seconds,
        run_timeout_seconds=timeout,
        result_retention_hours=result_retention,
        row_retention_days=row_retention,
    )
