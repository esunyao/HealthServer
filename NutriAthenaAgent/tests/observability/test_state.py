from __future__ import annotations

import io
import json
import logging
import subprocess
import sys

import pytest
from loguru import logger

from nutriathena_agent.observability import (
    DebugLevel, DebugTracer, configure_logging, log_context, log_event, reset_logging,
)


def _configure(stream: io.StringIO, **kwargs) -> None:
    configure_logging(sink=stream, log_format="json", file_path=None, color="never", force=True, **kwargs)


def test_reset_restores_every_intercepted_stdlib_logger():
    names = (
        "", "uvicorn", "uvicorn.error", "uvicorn.asgi", "uvicorn.access",
        "httpx", "httpcore", "mcp", "openai", "langchain", "langchain_core",
        "langgraph", "psycopg", "psycopg_pool", "urllib3",
    )
    saved = {
        name: (list(logging.getLogger(name).handlers), logging.getLogger(name).level, logging.getLogger(name).propagate)
        for name in names
    }
    first, second = io.StringIO(), io.StringIO()
    _configure(first, intercept_stdlib=True)
    _configure(second, intercept_stdlib=True)
    reset_logging()
    reset_logging()

    assert saved == {
        name: (list(logging.getLogger(name).handlers), logging.getLogger(name).level, logging.getLogger(name).propagate)
        for name in names
    }


def test_configure_and_reset_preserve_external_loguru_patcher_and_sink(monkeypatch):
    received: list[str] = []
    patcher = lambda record: record["extra"].update(external="preserved")
    monkeypatch.setattr(logger._core, "patcher", patcher)
    handler_id = logger.add(lambda message: received.append(str(message)), format="{extra[external]} {message}")
    try:
        stream = io.StringIO()
        _configure(stream)
        log_event("configured")
        assert json.loads(stream.getvalue())["external"] == "preserved"
        reset_logging()
        logger.info("after reset")
        assert logger._core.patcher is patcher
        assert any("preserved after reset" in item for item in received)
    finally:
        logger.remove(handler_id)


def test_force_reconfigure_removes_previous_sink_without_duplicate_records():
    first, second = io.StringIO(), io.StringIO()
    _configure(first)
    log_event("first")
    _configure(second)
    log_event("second")

    assert [json.loads(line)["event"] for line in first.getvalue().splitlines()] == ["first"]
    assert [json.loads(line)["event"] for line in second.getvalue().splitlines()] == ["second"]


def test_full_warning_once_per_lifecycle_and_content_mode_resets():
    stream = io.StringIO()
    _configure(stream, debug_level=DebugLevel.FULL)
    _configure(stream, debug_level=DebugLevel.FULL)
    assert stream.getvalue().count('"event": "logging.full_mode"') == 1
    reset_logging()
    _configure(stream, debug_level=DebugLevel.FULL)
    assert stream.getvalue().count('"event": "logging.full_mode"') == 2


def test_adding_interception_to_existing_configuration_is_idempotent():
    stream = io.StringIO()
    _configure(stream)
    configure_logging(intercept_stdlib=True)
    configure_logging(intercept_stdlib=True)
    logging.getLogger("uvicorn.error").info("once")
    logging.getLogger("uvicorn.access").info("hidden access")

    assert stream.getvalue().count('"message": "once"') == 1
    assert "hidden access" not in stream.getvalue()


def test_filtering_uses_selected_level_and_debug_lowers_it():
    first, second = io.StringIO(), io.StringIO()
    _configure(first, level="ERROR")
    log_event("hidden")
    log_event("visible", level="ERROR")
    _configure(second, debug_level=DebugLevel.TRACE, level="CRITICAL")
    DebugTracer(DebugLevel.TRACE).event("debug.visible")

    assert [json.loads(line)["event"] for line in first.getvalue().splitlines()] == ["visible"]
    assert json.loads(second.getvalue())["event"] == "debug.visible"


def test_log_event_attributes_original_caller():
    stream = io.StringIO()
    _configure(stream)
    expected_line = sys._getframe().f_lineno + 1
    log_event("caller")

    event = json.loads(stream.getvalue())
    assert event["logger"] == __name__
    assert event["function"] == "test_log_event_attributes_original_caller"
    assert event["line"] == expected_line


def test_logging_never_raises_for_unserializable_fields():
    class BadString:
        def __str__(self):
            raise ValueError("synthetic rendering failure")

    stream = io.StringIO()
    _configure(stream)
    log_event("bad", field=BadString())
    log_event("still.alive")
    assert json.loads(stream.getvalue())["event"] == "still.alive"


def test_imports_are_independent_of_configuration_and_legacy_modules():
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
from nutriathena_agent.observability import DebugLevel, DebugTraceCallback, log_event
for name in ('nutriathena_agent.' + suffix for suffix in ('config', 'logging_service', 'debug')):
    assert name not in sys.modules, name
assert DebugLevel.TRACE.value == 'trace'
"""],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 0, result.stderr


def test_external_loguru_records_use_safe_application_sinks():
    stream = io.StringIO()
    _configure(stream)
    with log_context(trace_id="external"):
        logger.warning("Bearer fake-token https://example.test/?token=hidden")

    event = json.loads(stream.getvalue())
    assert event["trace_id"] == "external"
    assert "fake-token" not in event["message"]
    assert "example.test" not in event["message"]
