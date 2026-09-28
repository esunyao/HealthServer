"""Durable PostgreSQL-backed worker with leases and fencing tokens."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import socket
from contextlib import suppress
from typing import Any
from uuid import uuid4

from .contracts import parse_meal_result, result_dict
from .database import Repository
from .meal_agent import MealRunner, run_meal_analysis
from .runtime_config import RuntimeSettings

logger = logging.getLogger(__name__)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class DurableWorker:
    def __init__(
        self,
        repository: Repository,
        settings: RuntimeSettings,
        *,
        runner: MealRunner | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.runner = runner
        self.owner = f"{socket.gethostname()}:{uuid4()}"
        self._stopping = asyncio.Event()

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                worked = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exception:
                # Avoid logging exception text: providers can include URLs or
                # other request data in third-party exception messages.
                logger.error("worker cycle failed (%s)", type(exception).__name__)
                worked = False
            if not worked:
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=self.settings.worker_poll_seconds)
                except TimeoutError:
                    pass

    async def stop(self) -> None:
        self._stopping.set()

    async def run_once(self) -> bool:
        await asyncio.to_thread(self.repository.interrupt_expired_leases)
        await asyncio.to_thread(self.repository.purge_expired_results)
        await asyncio.to_thread(self.repository.purge_expired_rows)
        row = await asyncio.to_thread(
            self.repository.claim_pending,
            self.owner,
            self.settings.lease_seconds,
        )
        if row is None:
            return False
        await self._execute(row)
        return True

    async def _execute(self, row: dict[str, Any]) -> None:
        run_id = row["run_id"]
        lease_version = row["lease_version"]
        attempt_id = str(row["attempt_id"])
        task_id = str(row["task_id"])
        payload = row["request_payload"]
        trace_id = payload.get("input", {}).get("trace_id", "")
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
                    logger.warning("worker lease heartbeat failed (%s)", type(exception).__name__)
                    lost_lease.set()
                    return
                if not valid:
                    lost_lease.set()
                    return
                if cancelled:
                    cancel_requested.set()
                    return

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
                    await self._finish_error(run_id, lease_version, "CANCELLED", "Cancellation was requested.", "interrupted")
                elif lost_lease.is_set() or (heartbeat_task in done and not analysis_task.done()):
                    await self._cancel_analysis(analysis_task)
                else:
                    await self._cancel_analysis(analysis_task)
                    await self._finish_error(run_id, lease_version, "AGENT_RUN_TIMEOUT", "The run exceeded its time limit.", "error")
                return

            try:
                result = analysis_task.result()
                if cancel_requested.is_set():
                    await self._finish_error(
                        run_id,
                        lease_version,
                        "CANCELLED",
                        "Cancellation was requested.",
                        "interrupted",
                    )
                    return
                if lost_lease.is_set():
                    logger.warning("run result discarded after its worker lease expired")
                    return
                parsed = parse_meal_result(_canonical_json(result))
                normalized = result_dict(parsed)
                digest = hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()
            except asyncio.CancelledError:
                raise
            except Exception as exception:
                logger.error("meal runner failed (%s)", type(exception).__name__)
                await self._finish_error(run_id, lease_version, "AGENT_RUN_FAILED", "The meal analysis run failed.", "error")
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
                logger.warning("run result discarded after lease or cancellation changed")
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
            logger.warning("terminal run update ignored after lease or cancellation changed")
