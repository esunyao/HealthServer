"""Durable PostgreSQL-backed worker with leases and fencing tokens."""

from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import time
from contextlib import suppress
from typing import Any
from uuid import uuid4

from ..config import RuntimeSettings
from ..contracts import parse_meal_result, result_dict
from ..logging_service import configure_logging, log_context, log_event, log_exception
from ..meal_agent import run_meal_analysis
from .ports import MealRunner, RunRepository
from .types import RuntimeIdentity


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class DurableWorker:
    def __init__(
        self,
        repository: RunRepository,
        settings: RuntimeSettings,
        *,
        artifact_sha256: str,
        runner: MealRunner | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.artifact_sha256 = artifact_sha256
        self.identity = RuntimeIdentity(
            release_id=settings.release_id,
            deployment_key=settings.deployment_key,
            assistant_id=settings.assistant_id,
            artifact_sha256=artifact_sha256,
        )
        self.runner = runner
        self.owner = f"{socket.gethostname()}:{uuid4()}"
        self._stopping = asyncio.Event()
        self._phase = "maintenance"
        configure_logging(settings.debug_level)

    async def run_forever(self) -> None:
        log_event(
            "worker.started",
            level="INFO",
            owner=self.owner,
            release_id=str(self.settings.release_id),
            deployment_key=self.settings.deployment_key,
            assistant_id=self.settings.assistant_id,
            artifact_sha256=self.artifact_sha256,
            poll_seconds=self.settings.worker_poll_seconds,
            lease_seconds=self.settings.lease_seconds,
            run_timeout_seconds=self.settings.run_timeout_seconds,
        )
        failure_count = 0
        try:
            while not self._stopping.is_set():
                try:
                    worked = await self.run_once()
                    failure_count = 0
                except asyncio.CancelledError:
                    raise
                except Exception as exception:
                    failure_count += 1
                    if failure_count == 1:
                        log_exception(
                            "worker.cycle.failed",
                            exception,
                            phase=self._phase,
                            failure_count=failure_count,
                        )
                    else:
                        log_event(
                            "worker.cycle.failed",
                            level="WARNING",
                            phase=self._phase,
                            failure_count=failure_count,
                            error_type=type(exception).__name__,
                            error_message=str(exception),
                        )
                    worked = False
                if not worked:
                    try:
                        await asyncio.wait_for(self._stopping.wait(), timeout=self.settings.worker_poll_seconds)
                    except TimeoutError:
                        pass
        finally:
            log_event("worker.stopped", level="INFO", owner=self.owner)

    async def stop(self) -> None:
        self._stopping.set()

    async def run_once(self) -> bool:
        self._phase = "maintenance"
        expired_leases = await asyncio.to_thread(self.repository.interrupt_expired_leases)
        purged_results = await asyncio.to_thread(self.repository.purge_expired_results)
        purged_runs, purged_threads = await asyncio.to_thread(self.repository.purge_expired_rows)
        if expired_leases or purged_results or purged_runs or purged_threads:
            log_event(
                "worker.maintenance",
                level="DEBUG",
                expired_leases=expired_leases,
                purged_results=purged_results,
                purged_runs=purged_runs,
                purged_threads=purged_threads,
            )
        self._phase = "claim"
        row = await asyncio.to_thread(
            self.repository.claim_pending,
            self.owner,
            self.settings.lease_seconds,
            release_id=self.settings.release_id,
            deployment_key=self.settings.deployment_key,
            assistant_id=self.settings.assistant_id,
            artifact_sha256=self.artifact_sha256,
        )
        if row is None:
            return False
        self._phase = "execute"
        log_event(
            "worker.run.claimed",
            level="INFO",
            run_id=str(row["run_id"]),
            thread_id=str(row.get("thread_id", "")),
            task_id=str(row["task_id"]),
            attempt_id=str(row["attempt_id"]),
            lease_version=row["lease_version"],
        )
        await self._execute(row)
        return True

    async def _execute(self, row: dict[str, Any]) -> None:
        run_id = row["run_id"]
        lease_version = row["lease_version"]
        attempt_id = str(row["attempt_id"])
        task_id = str(row["task_id"])
        thread_id = str(row.get("thread_id", ""))
        payload = row.get("request_payload") or {}
        trace_id = (payload.get("input") or {}).get("trace_id", "")
        started = time.perf_counter()

        with log_context(
            trace_id=trace_id or None,
            run_id=str(run_id),
            task_id=task_id,
            attempt_id=attempt_id,
        ):
            log_event(
                "worker.run.started",
                level="INFO",
                thread_id=thread_id,
                lease_version=lease_version,
            )
            if not self._matches_worker_identity(row):
                log_event(
                    "worker.run.identity_mismatch",
                    level="ERROR",
                    thread_id=thread_id,
                    expected_release_id=str(self.settings.release_id),
                    actual_release_id=str(row["release_id"]),
                    expected_deployment_key=self.settings.deployment_key,
                    actual_deployment_key=row["agent_deployment_key"],
                    expected_assistant_id=self.settings.assistant_id,
                    actual_assistant_id=row["agent_assistant_id"],
                    expected_artifact_sha256=self.artifact_sha256,
                    actual_artifact_sha256=row["agent_artifact_sha256"],
                )
                await self._finish_error(
                    run_id,
                    lease_version,
                    "RUN_IDENTITY_MISMATCH",
                    "Run identity does not match this worker.",
                    "error",
                )
                return

            lost_lease = asyncio.Event()
            cancel_requested = asyncio.Event()
            stop_heartbeat = asyncio.Event()

            async def heartbeat() -> None:
                interval = max(1.0, self.settings.lease_seconds / 3)
                while not stop_heartbeat.is_set():
                    try:
                        await asyncio.wait_for(stop_heartbeat.wait(), timeout=interval)
                        return
                    except TimeoutError:
                        pass
                    try:
                        valid, cancelled = await asyncio.to_thread(
                            self.repository.renew_lease,
                            run_id,
                            self.owner,
                            lease_version,
                            self.settings.lease_seconds,
                        )
                    except Exception as exception:
                        log_exception(
                            "worker.lease.lost",
                            exception,
                            level="WARNING",
                            reason="heartbeat_failed",
                            lease_version=lease_version,
                        )
                        lost_lease.set()
                        return
                    if not valid:
                        log_event(
                            "worker.lease.lost",
                            level="WARNING",
                            reason="invalid_lease",
                            lease_version=lease_version,
                        )
                        lost_lease.set()
                        return
                    if cancelled:
                        log_event(
                            "worker.lease.cancelled",
                            level="INFO",
                            lease_version=lease_version,
                        )
                        cancel_requested.set()
                        return
                    log_event(
                        "worker.lease.renewed",
                        level="DEBUG",
                        lease_version=lease_version,
                        lease_seconds=self.settings.lease_seconds,
                    )

            async def invoke_runner() -> dict[str, object]:
                if self.runner is None:
                    return await run_meal_analysis(
                        task_id=task_id,
                        attempt_id=attempt_id,
                        trace_id=trace_id,
                    )
                return await self.runner.run(task_id=task_id, attempt_id=attempt_id, trace_id=trace_id)

            analysis_task = asyncio.create_task(invoke_runner(), name=f"agent-run-{run_id}")
            heartbeat_task = asyncio.create_task(heartbeat(), name=f"agent-lease-{run_id}")
            try:
                done, _ = await asyncio.wait(
                    {analysis_task, heartbeat_task},
                    timeout=self.settings.run_timeout_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if analysis_task not in done:
                    if cancel_requested.is_set():
                        await self._cancel_analysis(analysis_task)
                        log_event(
                            "worker.run.cancelled",
                            level="INFO",
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                        await self._finish_error(
                            run_id,
                            lease_version,
                            "CANCELLED",
                            "Cancellation was requested.",
                            "interrupted",
                        )
                    elif lost_lease.is_set() or (heartbeat_task in done and not analysis_task.done()):
                        await self._cancel_analysis(analysis_task)
                        log_event(
                            "worker.run.lease_lost",
                            level="WARNING",
                            reason="heartbeat_stopped",
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                    else:
                        await self._cancel_analysis(analysis_task)
                        log_event(
                            "worker.run.timed_out",
                            level="WARNING",
                            timeout_seconds=self.settings.run_timeout_seconds,
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                        await self._finish_error(
                            run_id,
                            lease_version,
                            "AGENT_RUN_TIMEOUT",
                            "The run exceeded its time limit.",
                            "error",
                        )
                    return

                try:
                    result = analysis_task.result()
                except asyncio.CancelledError:
                    raise
                except Exception as exception:
                    log_event(
                        "worker.run.failed",
                        level="ERROR",
                        error_type=type(exception).__name__,
                        error_message=str(exception),
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                    log_exception(
                        "worker.run.failed.detail",
                        exception,
                        level="DEBUG",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                    await self._finish_error(
                        run_id,
                        lease_version,
                        "AGENT_RUN_FAILED",
                        "The meal analysis run failed.",
                        "error",
                    )
                    return

                if cancel_requested.is_set():
                    log_event(
                        "worker.run.cancelled",
                        level="INFO",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                    await self._finish_error(
                        run_id,
                        lease_version,
                        "CANCELLED",
                        "Cancellation was requested.",
                        "interrupted",
                    )
                    return
                if lost_lease.is_set():
                    log_event(
                        "worker.run.lease_lost",
                        level="WARNING",
                        reason="result_discarded",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                    return

                try:
                    parsed = parse_meal_result(_canonical_json(result))
                    normalized = result_dict(parsed)
                    digest = hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()
                except asyncio.CancelledError:
                    raise
                except Exception as exception:
                    log_exception(
                        "worker.run.result_invalid",
                        exception,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                    await self._finish_error(
                        run_id,
                        lease_version,
                        "AGENT_RUN_FAILED",
                        "The meal analysis run failed.",
                        "error",
                    )
                    return

                committed = await asyncio.to_thread(
                    self.repository.finish_success,
                    run_id,
                    self.owner,
                    lease_version,
                    normalized,
                    digest,
                )
                if not committed:
                    log_event(
                        "worker.run.discarded",
                        level="WARNING",
                        reason="lease_or_cancellation_changed",
                    )
                    return
                item_count = len(normalized.get("items", [])) if isinstance(normalized.get("items"), list) else 0
                log_event(
                    "worker.run.succeeded",
                    level="INFO",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    result_status=normalized.get("status", "analysis"),
                    item_count=item_count,
                )
            finally:
                stop_heartbeat.set()
                if not analysis_task.done():
                    analysis_task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await analysis_task
                if not heartbeat_task.done():
                    heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task

    def _matches_worker_identity(self, row: dict[str, Any]) -> bool:
        return self.identity.matches(row)

    @staticmethod
    async def _cancel_analysis(task: asyncio.Task[Any]) -> None:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task

    async def _finish_error(
        self,
        run_id: Any,
        lease_version: int,
        code: str,
        message: str,
        status: str,
    ) -> None:
        committed = await asyncio.to_thread(
            self.repository.finish_terminal,
            run_id,
            self.owner,
            lease_version,
            status=status,
            error_code=code,
            error_message=message,
        )
        if not committed:
            log_event(
                "worker.run.discarded",
                level="WARNING",
                reason="terminal_update_ignored",
                error_code=code,
            )
