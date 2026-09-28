"""HealthMind-compatible run API for the durable NutriAthenaAgent service."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .artifact import compute_artifact_sha256
from .auth import TokenVerifier
from .database import ConflictError, Repository
from .migrations import apply_migrations
from .models import RunCreateRequest, ThreadCreateRequest
from .runtime_config import RuntimeSettings, load_runtime_settings
from .worker import DurableWorker

_bearer = HTTPBearer(auto_error=False)


def _time(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _run_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(row["run_id"]),
        "thread_id": str(row["thread_id"]),
        "task_id": str(row["task_id"]),
        "attempt_id": str(row["attempt_id"]),
        "assistant_id": row["agent_assistant_id"],
        "status": row["status"],
        "metadata": {
            "task_id": str(row["task_id"]),
            "attempt_id": str(row["attempt_id"]),
            "release_id": str(row["release_id"]),
            "artifact_sha256": row["agent_artifact_sha256"].strip(),
        },
        "created_at": _time(row["created_at"]),
        "started_at": _time(row.get("started_at")),
        "completed_at": _time(row.get("completed_at")),
        "error_code": row.get("error_code"),
        "error_message": row.get("error_message"),
    }


def create_app(
    *,
    settings: RuntimeSettings | None = None,
    repository: Repository | None = None,
    runner: Any | None = None,
    token_verifier: Any | None = None,
    start_worker: bool = True,
    artifact_sha256: str | None = None,
) -> FastAPI:
    settings = settings or load_runtime_settings()
    owns_repository = repository is None
    repository = repository or Repository(
        settings.database_url,
        row_retention_days=settings.row_retention_days,
        result_retention_hours=settings.result_retention_hours,
    )
    token_verifier = token_verifier or TokenVerifier(settings)
    artifact_sha = artifact_sha256 or compute_artifact_sha256()
    worker = DurableWorker(repository, settings, runner=runner) if start_worker else None
    worker_task: asyncio.Task[None] | None = None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal worker_task
        if owns_repository:
            await asyncio.to_thread(repository.open)
            await asyncio.to_thread(repository.assert_schema_ready)
        if worker is not None:
            worker_task = asyncio.create_task(worker.run_forever(), name="nutriathena-agent-worker")
        try:
            yield
        finally:
            if worker is not None:
                await worker.stop()
            if worker_task is not None:
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
            if owns_repository:
                await asyncio.to_thread(repository.close)

    app = FastAPI(title="NutriAthenaAgent", version="1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.repository = repository
    app.state.token_verifier = token_verifier
    app.state.artifact_sha256 = artifact_sha
    app.state.worker = worker

    async def authorize(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    ) -> dict[str, Any]:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await request.app.state.token_verifier.verify(credentials.credentials)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        try:
            ready = await asyncio.to_thread(repository.health_check)
        except Exception:
            ready = False
        if not ready:
            raise HTTPException(status_code=503, detail="Database unavailable")
        return {"status": "ok"}

    @app.post("/threads", status_code=200)
    async def create_thread(
        body: ThreadCreateRequest,
        _: dict[str, Any] = Depends(authorize),
    ) -> dict[str, str]:
        attempt_id = body.metadata.attempt_id or body.thread_id
        if body.thread_id != attempt_id:
            raise HTTPException(status_code=409, detail={"code": "THREAD_IDENTITY_CONFLICT"})
        try:
            await asyncio.to_thread(
                repository.create_thread,
                body.thread_id,
                body.metadata.task_id,
                attempt_id,
            )
        except ConflictError as exception:
            raise HTTPException(status_code=409, detail={"code": "THREAD_IDENTITY_CONFLICT"}) from exception
        return {"thread_id": str(body.thread_id)}

    @app.get("/threads/{thread_id}")
    async def get_thread(
        thread_id: UUID,
        _: dict[str, Any] = Depends(authorize),
    ) -> dict[str, Any]:
        row = await asyncio.to_thread(repository.get_thread, thread_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        return {
            "thread_id": str(row["thread_id"]),
            "task_id": str(row["task_id"]),
            "attempt_id": str(row["attempt_id"]),
        }

    @app.post("/threads/{thread_id}/runs", status_code=200)
    async def create_run(
        thread_id: UUID,
        body: RunCreateRequest,
        idempotency_key: str = Header(alias="Idempotency-Key"),
        _: dict[str, Any] = Depends(authorize),
    ) -> dict[str, Any]:
        if (
            body.input.task_id != body.metadata.task_id
            or body.input.attempt_id != body.metadata.attempt_id
            or thread_id != body.input.attempt_id
            or idempotency_key != str(body.input.attempt_id)
        ):
            raise HTTPException(status_code=409, detail={"code": "RUN_IDENTITY_CONFLICT"})
        if body.assistant_id != settings.assistant_id:
            raise HTTPException(status_code=409, detail={"code": "ASSISTANT_ID_MISMATCH"})
        if body.metadata.release_id != settings.release_id:
            raise HTTPException(status_code=409, detail={"code": "RELEASE_ID_MISMATCH"})
        if body.metadata.artifact_sha256 != artifact_sha:
            raise HTTPException(status_code=409, detail={"code": "ARTIFACT_DIGEST_MISMATCH"})
        canonical = json.dumps(
            body.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        try:
            row, _ = await asyncio.to_thread(
                repository.submit_run,
                thread_id=thread_id,
                task_id=body.input.task_id,
                attempt_id=body.input.attempt_id,
                release_id=body.metadata.release_id,
                request_payload=body.model_dump(mode="json"),
                request_sha256=request_hash,
                requested_assistant_id=body.assistant_id,
                requested_artifact_sha256=body.metadata.artifact_sha256,
                deployment_key=settings.deployment_key,
                assistant_id=settings.assistant_id,
                artifact_sha256=artifact_sha,
            )
        except ConflictError as exception:
            if str(exception) == "IDEMPOTENCY_CONFLICT":
                raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_CONFLICT"}) from exception
            raise HTTPException(status_code=409, detail={"code": "THREAD_IDENTITY_CONFLICT"}) from exception
        return _run_response(row)

    @app.get("/threads/{thread_id}/runs")
    async def list_runs(
        thread_id: UUID,
        _: dict[str, Any] = Depends(authorize),
    ) -> list[dict[str, Any]]:
        thread = await asyncio.to_thread(repository.get_thread, thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        rows = await asyncio.to_thread(repository.list_runs, thread_id)
        return [_run_response(row) for row in rows]

    @app.get("/runs/{run_id}")
    async def get_run(
        run_id: UUID,
        _: dict[str, Any] = Depends(authorize),
    ) -> dict[str, Any]:
        row = await asyncio.to_thread(repository.get_run, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return _run_response(row)

    @app.get("/runs/{run_id}/wait")
    async def wait_run(
        run_id: UUID,
        timeout_seconds: int = Query(default=120, ge=1, le=600),
        _: dict[str, Any] = Depends(authorize),
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            row = await asyncio.to_thread(repository.get_run, run_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Run not found")
            if row["status"] == "success":
                if row["result_payload"] is None:
                    raise HTTPException(status_code=410, detail={"code": "RESULT_EXPIRED"})
                return {"output": row["result_payload"]}
            if row["status"] in {"error", "interrupted"}:
                raise HTTPException(
                    status_code=409,
                    detail={"code": row["error_code"], "status": row["status"]},
                )
            if asyncio.get_running_loop().time() >= deadline:
                return {"status": row["status"], "run_id": str(row["run_id"])}
            await asyncio.sleep(0.25)

    @app.post("/runs/{run_id}/cancel")
    async def cancel_run(
        run_id: UUID,
        _: dict[str, Any] = Depends(authorize),
    ) -> dict[str, Any]:
        row = await asyncio.to_thread(repository.request_cancel, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return _run_response(row)

    return app


def migrate_database(database_url: str) -> list[str]:
    """Apply checked-in SQL migrations; called explicitly by the CLI."""
    repository = Repository(database_url)
    repository.open()
    try:
        return apply_migrations(repository.pool)
    finally:
        repository.close()
