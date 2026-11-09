from __future__ import annotations

import asyncio
import io
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from nutriathena_agent.observability import (
    DebugLevel, configure_logging, log_context, log_event, log_exception,
)


def _capture() -> io.StringIO:
    stream = io.StringIO()
    configure_logging(
        DebugLevel.TRACE, sink=stream, log_format="json", level="DEBUG",
        file_path=None, color="never", force=True,
    )
    return stream


def _events(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_nested_context_restores_fields_after_exception():
    stream = _capture()
    with log_context(trace_id="outer", run_id="run", task_id=None, attempt_id=""):
        with pytest.raises(RuntimeError):
            with log_context(trace_id="inner", task_id="task", run_id=None):
                log_event("inner", trace_id="explicit", task_id=None)
                raise RuntimeError("unwind")
        log_event("outer")
    log_event("outside")

    inner, outer, outside = _events(stream)
    assert inner["trace_id"] == "explicit"
    assert inner["run_id"] == "run"
    assert inner["task_id"] == "task"
    assert outer["trace_id"] == "outer"
    assert outer["run_id"] == "run"
    assert "task_id" not in outer
    assert "attempt_id" not in outer
    assert all(key not in outside for key in ("trace_id", "run_id", "task_id", "attempt_id"))


def test_concurrent_async_tasks_keep_context_across_suspension_and_failure():
    stream = _capture()

    async def scenario() -> None:
        ready = asyncio.Event()
        started = 0

        async def run(index: int) -> None:
            nonlocal started
            with log_context(trace_id=f"trace-{index}", run_id=f"run-{index}"):
                started += 1
                if started == 8:
                    ready.set()
                await ready.wait()
                for step in range(3):
                    await asyncio.sleep(0)
                    log_event("task.step", index=index, step=step)
                log_exception("task.failure", RuntimeError("synthetic"), index=index)
            log_event("task.outside", index=index)

        with log_context(task_id="parent-task"):
            await asyncio.gather(*(run(index) for index in range(8)))
            log_event("parent")
        log_event("outside")

    asyncio.run(scenario())

    events = _events(stream)
    for event in events:
        if event["event"] in {"task.step", "task.failure"}:
            assert event["trace_id"] == f"trace-{event['index']}"
            assert event["run_id"] == f"run-{event['index']}"
            assert event["task_id"] == "parent-task"
        elif event["event"] in {"parent", "task.outside"}:
            assert event["task_id"] == "parent-task"
            assert "trace_id" not in event
            assert "run_id" not in event
        else:
            assert "task_id" not in event
    assert len([event for event in events if event["event"] == "task.step"]) == 24
    assert len([event for event in events if event["event"] == "task.failure"]) == 8


def test_concurrent_threads_do_not_share_context_with_each_other_or_parent():
    stream = _capture()
    barrier = Barrier(4)

    def run(index: int) -> None:
        with log_context(trace_id=f"thread-{index}", attempt_id=f"attempt-{index}"):
            barrier.wait(timeout=5)
            log_event("thread", index=index)
        log_event("thread.outside", index=index)

    with log_context(trace_id="parent", task_id="parent-task"):
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(run, range(4)))
        log_event("parent")

    for event in _events(stream):
        if event["event"] == "thread":
            assert event["trace_id"] == f"thread-{event['index']}"
            assert event["attempt_id"] == f"attempt-{event['index']}"
            assert "task_id" not in event
        elif event["event"] == "thread.outside":
            assert "trace_id" not in event
            assert "attempt_id" not in event
            assert "task_id" not in event
        else:
            assert event["trace_id"] == "parent"
            assert event["task_id"] == "parent-task"


def test_cancelled_async_task_restores_inherited_context():
    stream = _capture()

    async def scenario() -> None:
        ready = asyncio.Event()

        async def run() -> None:
            try:
                with log_context(run_id="cancelled"):
                    ready.set()
                    await asyncio.Future()
            finally:
                log_event("cancelled.finally")

        with log_context(trace_id="parent"):
            task = asyncio.create_task(run())
            await ready.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            log_event("parent")

    asyncio.run(scenario())

    events = _events(stream)
    assert [event["event"] for event in events] == ["cancelled.finally", "parent"]
    assert all(event["trace_id"] == "parent" for event in events)
    assert all("run_id" not in event for event in events)
