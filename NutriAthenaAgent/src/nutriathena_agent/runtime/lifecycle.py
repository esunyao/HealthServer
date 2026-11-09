"""Own resources for one application lifespan, including partial startup failure."""

import asyncio
import time
from contextlib import AsyncExitStack, asynccontextmanager

from ..observability import log_event, log_exception


async def _stop_worker(worker, task):
    try:
        await worker.stop()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exception:
            log_exception("worker.shutdown.failed", exception)


@asynccontextmanager
async def lifespan(app):
    resources = app.state.runtime
    async with AsyncExitStack() as stack:
        if resources.owns_repository:
            stack.push_async_callback(asyncio.to_thread, resources.repository.close)
            started = time.perf_counter()
            try:
                await asyncio.to_thread(resources.repository.open)
                await asyncio.to_thread(resources.repository.assert_schema_ready)
            except Exception as exception:
                log_exception("service.database.failed", exception)
                raise
            log_event(
                "service.database.ready",
                level="INFO",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        if resources.worker is not None:
            task = asyncio.create_task(
                resources.worker.run_forever(), name="nutriathena-agent-worker"
            )
            stack.push_async_callback(_stop_worker, resources.worker, task)
        log_event(
            "service.started",
            level="INFO",
            host=resources.settings.host,
            port=resources.settings.port,
            worker=resources.worker is not None,
        )
        try:
            yield
        finally:
            log_event("service.stopping", level="INFO")
    app.state.health_failure_logged = False
    log_event("service.stopped", level="INFO")
