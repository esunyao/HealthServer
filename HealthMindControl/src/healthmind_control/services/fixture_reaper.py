import asyncio
from contextlib import suppress


class FixtureSessionReaper:
    """在 HealthMind 一小时 attempt 超时扫描之前结束 HMC 的短期 MCP 测试记录。"""

    def __init__(self, repo, audit, interval_seconds: int):
        self.repo = repo
        self.audit = audit
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None

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
                for task_id in await self.repo.close_expired_mcp_sessions():
                    self.audit.write(
                        "fixture.mcp.expire", task_id, "MCP 调试租期到期", "succeeded",
                    )
            except Exception as exc:
                self.audit.write("fixture.mcp.expire", "scan", "MCP 调试租期扫描", "failed", error=str(exc))
