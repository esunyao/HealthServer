import asyncio
import logging
from contextlib import suppress


class FixtureSessionReaper:
    """在 HealthMind 一小时 attempt 超时扫描之前结束 HMC 的短期 MCP 测试记录。"""

    def __init__(self, repo, audit, interval_seconds: int):
        self.repo = repo
        self.audit = audit
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._logger = logging.getLogger(__name__)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                expired = await self.repo.close_expired_mcp_sessions()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.exception("MCP fixture expiry scan failed: %s", exc)
                await self._record("scan", "failed", error=str(exc))
                continue
            for task_id in expired:
                await self._record(task_id, "succeeded")

    async def _record(self, target: str, outcome: str, **details) -> None:
        try:
            await self.audit.write("fixture.mcp.expire", target, "MCP 调试租期扫描", outcome, **details)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Never allow best-effort audit I/O to terminate the reaper task.
            self._logger.exception("MCP fixture reaper audit write failed: %s", exc)
