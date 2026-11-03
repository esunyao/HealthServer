"""HealthMind-compatible run API for the durable NutriAthenaAgent service."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .artifact import compute_artifact_sha256
from .auth import TokenVerifier
from .database import ConflictError, Repository
from .logging_service import log_context, log_event, log_exception
from .migrations import apply_migrations
from .models import RunCreateRequest, RunResponse, ThreadCreateRequest, ThreadResponse
from .runtime_config import RuntimeSettings, load_runtime_settings
from .worker import DurableWorker

_bearer = HTTPBearer(auto_error=False)
_TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _request_trace_id(request: Request) -> str:
    for name in ("x-trace-id", "x-request-id"):
        value = request.headers.get(name, "").strip()
        if value and _TRACE_ID_PATTERN.fullmatch(value):
            return value
    return uuid4().hex


def _status_level(status_code: int) -> str:
    if status_code >= 500:
        return "ERROR"
    if status_code >= 400:
        return "WARNING"
    return "INFO"


def _thread_response(row: dict[str, Any]) -> ThreadResponse:
    return ThreadResponse(
        thread_id=row["thread_id"],
        metadata={
            "task_id": row["task_id"],
            "attempt_id": row["attempt_id"],
        },
    )


def _run_response(row: dict[str, Any]) -> RunResponse:
    return RunResponse(
        run_id=row["run_id"],
        thread_id=row["thread_id"],
        task_id=row["task_id"],
        attempt_id=row["attempt_id"],
        assistant_id=row["agent_assistant_id"],
        status=row["status"],
        metadata={
            "task_id": row["task_id"],
            "attempt_id": row["attempt_id"],
            "release_id": row["release_id"],
            "artifact_sha256": row["agent_artifact_sha256"].strip(),
        },
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
    )


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
    worker = (
        DurableWorker(repository, settings, artifact_sha256=artifact_sha, runner=runner)
        if start_worker
        else None
    )
    worker_task: asyncio.Task[None] | None = None
    health_failure_logged = False

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal worker_task, health_failure_logged
        if owns_repository:
            started = time.perf_counter()
            try:
                await asyncio.to_thread(repository.open)
                await asyncio.to_thread(repository.assert_schema_ready)
            except Exception as exception:
                log_exception("service.database.failed", exception)
                raise
            log_event(
                "service.database.ready",
                level="INFO",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        if worker is not None:
            worker_task = asyncio.create_task(worker.run_forever(), name="nutriathena-agent-worker")
        log_event(
            "service.started",
            level="INFO",
            host=settings.host,
            port=settings.port,
            worker=worker is not None,
        )
        try:
            yield
        finally:
            log_event("service.stopping", level="INFO")
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
            health_failure_logged = False
            log_event("service.stopped", level="INFO")

    app = FastAPI(title="NutriAthenaAgent", version="1.0", lifespan=lifespan)

    @app.middleware("http")
    async def log_request(request: Request, call_next: Any) -> Any:
        trace_id = _request_trace_id(request)
        path = request.url.path
        started = time.perf_counter()
        with log_context(trace_id=trace_id):
            log_event(
                "http.request.started",
                level="DEBUG",
                method=request.method,
                path=path,
            )
            try:
                response = await call_next(request)
            except Exception as exception:
                log_exception(
                    "http.request.failed",
                    exception,
                    method=request.method,
                    path=path,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
                raise
            level = "DEBUG" if path == "/healthz" else _status_level(response.status_code)
            log_event(
                "http.request.finished",
                level=level,
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            response.headers["X-Request-Id"] = trace_id
            return response

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
        nonlocal health_failure_logged
        try:
            ready = await asyncio.to_thread(repository.health_check)
        except Exception as exception:
            ready = False
            if not health_failure_logged:
                health_failure_logged = True
                log_exception("healthz.database_unavailable", exception, level="WARNING")
            else:
                log_event(
                    "healthz.database_unavailable",
                    level="DEBUG",
                    error_type=type(exception).__name__,
                )
        if not ready:
            if not health_failure_logged:
                health_failure_logged = True
                log_event(
                    "healthz.database_unavailable",
                    level="WARNING",
                    message="Database health check returned false",
                )
            raise HTTPException(status_code=503, detail="Database unavailable")
        health_failure_logged = False
        return {"status": "ok"}

    @app.post("/threads", status_code=200, response_model=ThreadResponse)
    async def create_thread(
        body: ThreadCreateRequest,
        _: dict[str, Any] = Depends(authorize),
    ) -> ThreadResponse:
        attempt_id = body.metadata.attempt_id or body.thread_id
        if body.thread_id != attempt_id:
            log_event(
                "thread.identity_conflict",
                level="WARNING",
                error_code="THREAD_IDENTITY_CONFLICT",
                thread_id=str(body.thread_id),
                task_id=str(body.metadata.task_id),
                attempt_id=str(attempt_id),
            )
            raise HTTPException(status_code=409, detail={"code": "THREAD_IDENTITY_CONFLICT"})
        try:
            row = await asyncio.to_thread(
                repository.create_thread,
                body.thread_id,
                body.metadata.task_id,
                attempt_id,
            )
        except ConflictError as exception:
            log_event(
                "thread.identity_conflict",
                level="WARNING",
                error_code="THREAD_IDENTITY_CONFLICT",
                thread_id=str(body.thread_id),
                task_id=str(body.metadata.task_id),
                attempt_id=str(attempt_id),
            )
            raise HTTPException(status_code=409, detail={"code": "THREAD_IDENTITY_CONFLICT"}) from exception
        log_event(
            "thread.ready",
            level="INFO",
            thread_id=str(row["thread_id"]),
            task_id=str(row["task_id"]),
            attempt_id=str(row["attempt_id"]),
        )
        return _thread_response(row)

    @app.get("/threads/{thread_id}", response_model=ThreadResponse)
    async def get_thread(
        thread_id: UUID,
        _: dict[str, Any] = Depends(authorize),
    ) -> ThreadResponse:
        row = await asyncio.to_thread(repository.get_thread, thread_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        return _thread_response(row)

    @app.post("/threads/{thread_id}/runs", status_code=200, response_model=RunResponse)
    async def create_run(
        thread_id: UUID,
        body: RunCreateRequest,
        idempotency_key: str = Header(alias="Idempotency-Key"),
        _: dict[str, Any] = Depends(authorize),
    ) -> RunResponse:
        if (
            body.input.task_id != body.metadata.task_id
            or body.input.attempt_id != body.metadata.attempt_id
            or thread_id != body.input.attempt_id
            or idempotency_key != str(body.input.attempt_id)
        ):
            log_event(
                "run.identity_conflict",
                level="WARNING",
                error_code="RUN_IDENTITY_CONFLICT",
                thread_id=str(thread_id),
                task_id=str(body.input.task_id),
                attempt_id=str(body.input.attempt_id),
            )
            raise HTTPException(status_code=409, detail={"code": "RUN_IDENTITY_CONFLICT"})
        if body.assistant_id != settings.assistant_id:
            log_event(
                "run.identity_conflict",
                level="WARNING",
                error_code="ASSISTANT_ID_MISMATCH",
                thread_id=str(thread_id),
                requested_assistant_id=body.assistant_id,
            )
            raise HTTPException(status_code=409, detail={"code": "ASSISTANT_ID_MISMATCH"})
        if body.metadata.release_id != settings.release_id:
            log_event(
                "run.identity_conflict",
                level="WARNING",
                error_code="RELEASE_ID_MISMATCH",
                thread_id=str(thread_id),
                requested_release_id=str(body.metadata.release_id),
            )
            raise HTTPException(status_code=409, detail={"code": "RELEASE_ID_MISMATCH"})
        if body.metadata.artifact_sha256 != artifact_sha:
            log_event(
                "run.identity_conflict",
                level="WARNING",
                error_code="ARTIFACT_DIGEST_MISMATCH",
                thread_id=str(thread_id),
                requested_artifact_sha256=body.metadata.artifact_sha256,
            )
            raise HTTPException(status_code=409, detail={"code": "ARTIFACT_DIGEST_MISMATCH"})
        canonical = json.dumps(
            body.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        try:
            row, created = await asyncio.to_thread(
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
            code = "IDEMPOTENCY_CONFLICT" if str(exception) == "IDEMPOTENCY_CONFLICT" else "THREAD_IDENTITY_CONFLICT"
            log_event(
                "run.identity_conflict",
                level="WARNING",
                error_code=code,
                thread_id=str(thread_id),
                task_id=str(body.input.task_id),
                attempt_id=str(body.input.attempt_id),
            )
            raise HTTPException(status_code=409, detail={"code": code}) from exception
        log_event(
            "run.submitted",
            level="INFO",
            run_id=str(row["run_id"]),
            thread_id=str(row["thread_id"]),
            task_id=str(row["task_id"]),
            attempt_id=str(row["attempt_id"]),
            created=created,
            status=row["status"],
        )
        return _run_response(row)

    @app.get("/threads/{thread_id}/runs", response_model=list[RunResponse])
    async def list_runs(
        thread_id: UUID,
        _: dict[str, Any] = Depends(authorize),
    ) -> list[RunResponse]:
        thread = await asyncio.to_thread(repository.get_thread, thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        rows = await asyncio.to_thread(repository.list_runs, thread_id)
        return [_run_response(row) for row in rows]

    @app.get("/runs/{run_id}", response_model=RunResponse)
    async def get_run(
        run_id: UUID,
        _: dict[str, Any] = Depends(authorize),
    ) -> RunResponse:
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

    @app.post("/runs/{run_id}/cancel", response_model=RunResponse)
    async def cancel_run(
        run_id: UUID,
        _: dict[str, Any] = Depends(authorize),
    ) -> RunResponse:
        row = await asyncio.to_thread(repository.request_cancel, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        log_event(
            "run.cancel_requested",
            level="INFO",
            run_id=str(row["run_id"]),
            status=row["status"],
        )
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
