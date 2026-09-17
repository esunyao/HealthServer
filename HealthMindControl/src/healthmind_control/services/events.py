import asyncio
from contextlib import suppress
from typing import Any


class StatusBroadcaster:
    """One database poll fan-outs to every SSE client."""

    def __init__(self, repo, interval: int):
        self.repo, self.interval = repo, interval
        self.subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self.task: asyncio.Task | None = None

    def start(self) -> None:
        self.task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.subscribers.discard(queue)

    async def _run(self) -> None:
        while True:
            if not self.subscribers:
                await asyncio.sleep(self.interval)
                continue
            try:
                payload = await self.repo.status_light()
            except Exception as exc:
                payload = {"error": str(exc)}
            for queue in tuple(self.subscribers):
                if queue.full():
                    with suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                queue.put_nowait(payload)
            await asyncio.sleep(self.interval)
