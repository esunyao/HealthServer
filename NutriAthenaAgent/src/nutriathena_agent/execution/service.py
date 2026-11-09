"""Run coordination independent of HTTP and PostgreSQL adapters."""

from __future__ import annotations
import asyncio
import hashlib
import json
from uuid import UUID
from ..observability import log_event
from .ports import RunRepository
from .types import ConflictError, RunServiceError, RunSubmission, RuntimeIdentity


class RunService:
    def __init__(self, repository: RunRepository, identity: RuntimeIdentity):
        self.repository = repository
        self.identity = identity

    async def create_thread(
        self, thread_id: UUID, task_id: UUID, attempt_id: UUID | None = None
    ):
        attempt_id = attempt_id or thread_id
        if thread_id != attempt_id:
            log_event(
                "thread.identity_conflict",
                level="WARNING",
                error_code="THREAD_IDENTITY_CONFLICT",
                thread_id=str(thread_id),
                task_id=str(task_id),
                attempt_id=str(attempt_id),
            )
            raise RunServiceError(
                status_code=409, detail={"code": "THREAD_IDENTITY_CONFLICT"}
            )
        try:
            row = await asyncio.to_thread(
                self.repository.create_thread, thread_id, task_id, attempt_id
            )
        except ConflictError as exception:
            log_event(
                "thread.identity_conflict",
                level="WARNING",
                error_code="THREAD_IDENTITY_CONFLICT",
                thread_id=str(thread_id),
                task_id=str(task_id),
                attempt_id=str(attempt_id),
            )
            raise RunServiceError(
                status_code=409, detail={"code": "THREAD_IDENTITY_CONFLICT"}
            ) from exception
        log_event(
            "thread.ready",
            level="INFO",
            thread_id=str(row["thread_id"]),
            task_id=str(row["task_id"]),
            attempt_id=str(row["attempt_id"]),
        )
        return row

    async def get_thread(self, thread_id: UUID):
        row = await asyncio.to_thread(self.repository.get_thread, thread_id)
        if row is None:
            raise RunServiceError(status_code=404, detail="Thread not found")
        return row

    async def create_run(
        self, thread_id: UUID, command: RunSubmission, idempotency_key: str
    ):
        if (
            command.task_id != command.metadata_task_id
            or command.attempt_id != command.metadata_attempt_id
            or thread_id != command.attempt_id
            or (idempotency_key != str(command.attempt_id))
        ):
            log_event(
                "run.identity_conflict",
                level="WARNING",
                error_code="RUN_IDENTITY_CONFLICT",
                thread_id=str(thread_id),
                task_id=str(command.task_id),
                attempt_id=str(command.attempt_id),
            )
            raise RunServiceError(
                status_code=409, detail={"code": "RUN_IDENTITY_CONFLICT"}
            )
        if command.assistant_id != self.identity.assistant_id:
            log_event(
                "run.identity_conflict",
                level="WARNING",
                error_code="ASSISTANT_ID_MISMATCH",
                thread_id=str(thread_id),
                requested_assistant_id=command.assistant_id,
            )
            raise RunServiceError(
                status_code=409, detail={"code": "ASSISTANT_ID_MISMATCH"}
            )
        if command.release_id != self.identity.release_id:
            log_event(
                "run.identity_conflict",
                level="WARNING",
                error_code="RELEASE_ID_MISMATCH",
                thread_id=str(thread_id),
                requested_release_id=str(command.release_id),
            )
            raise RunServiceError(
                status_code=409, detail={"code": "RELEASE_ID_MISMATCH"}
            )
        if command.artifact_sha256 != self.identity.artifact_sha256:
            log_event(
                "run.identity_conflict",
                level="WARNING",
                error_code="ARTIFACT_DIGEST_MISMATCH",
                thread_id=str(thread_id),
                requested_artifact_sha256=command.artifact_sha256,
            )
            raise RunServiceError(
                status_code=409, detail={"code": "ARTIFACT_DIGEST_MISMATCH"}
            )
        canonical = json.dumps(
            command.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        try:
            row, created = await asyncio.to_thread(
                self.repository.submit_run,
                thread_id=thread_id,
                task_id=command.task_id,
                attempt_id=command.attempt_id,
                release_id=command.release_id,
                request_payload=command.payload,
                request_sha256=request_hash,
                requested_assistant_id=command.assistant_id,
                requested_artifact_sha256=command.artifact_sha256,
                deployment_key=self.identity.deployment_key,
                assistant_id=self.identity.assistant_id,
                artifact_sha256=self.identity.artifact_sha256,
            )
        except ConflictError as exception:
            code = (
                "IDEMPOTENCY_CONFLICT"
                if str(exception) == "IDEMPOTENCY_CONFLICT"
                else "THREAD_IDENTITY_CONFLICT"
            )
            log_event(
                "run.identity_conflict",
                level="WARNING",
                error_code=code,
                thread_id=str(thread_id),
                task_id=str(command.task_id),
                attempt_id=str(command.attempt_id),
            )
            raise RunServiceError(status_code=409, detail={"code": code}) from exception
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
        return row

    async def list_runs(self, thread_id: UUID):
        thread = await asyncio.to_thread(self.repository.get_thread, thread_id)
        if thread is None:
            raise RunServiceError(status_code=404, detail="Thread not found")
        rows = await asyncio.to_thread(self.repository.list_runs, thread_id)
        return rows

    async def get_run(self, run_id: UUID):
        row = await asyncio.to_thread(self.repository.get_run, run_id)
        if row is None:
            raise RunServiceError(status_code=404, detail="Run not found")
        return row

    async def wait_run(self, run_id: UUID, timeout_seconds: int = 120):
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            row = await asyncio.to_thread(self.repository.get_run, run_id)
            if row is None:
                raise RunServiceError(status_code=404, detail="Run not found")
            if row["status"] == "success":
                if row["result_payload"] is None:
                    raise RunServiceError(
                        status_code=410, detail={"code": "RESULT_EXPIRED"}
                    )
                return {"output": row["result_payload"]}
            if row["status"] in {"error", "interrupted"}:
                raise RunServiceError(
                    status_code=409,
                    detail={"code": row["error_code"], "status": row["status"]},
                )
            if asyncio.get_running_loop().time() >= deadline:
                return {"status": row["status"], "run_id": str(row["run_id"])}
            await asyncio.sleep(0.25)

    async def cancel_run(self, run_id: UUID):
        row = await asyncio.to_thread(self.repository.request_cancel, run_id)
        if row is None:
            raise RunServiceError(status_code=404, detail="Run not found")
        log_event(
            "run.cancel_requested",
            level="INFO",
            run_id=str(row["run_id"]),
            status=row["status"],
        )
        return row
