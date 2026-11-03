from __future__ import annotations

import asyncio
import io
import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from loguru import logger
from pydantic import BaseModel, ValidationError

from nutriathena_agent.logging_service import (
    DebugLevel,
    LogFormat,
    configure_logging,
    log_context,
    log_event,
    log_exception,
)
from nutriathena_agent.mcp_tools import McpSetupError, connect_healthmind_mcp

_TASK_ID = "11111111-1111-4111-8111-111111111111"
_ATTEMPT_ID = "22222222-2222-4222-8222-222222222222"


def _capture(
    level: DebugLevel = DebugLevel.TRACE,
    log_format: LogFormat = LogFormat.TEXT,
) -> io.StringIO:
    stream = io.StringIO()
    configure_logging(
        level,
        sink=stream,
        log_format=log_format,
        level="DEBUG",
        file_path=None,
        force=True,
    )
    return stream


def test_text_event_contains_context_and_fields():
    stream = _capture()
    with log_context(trace_id="trace-1", run_id="run-1"):
        log_event("meal.started", model="test-model", attempt_id="attempt-1")

    output = stream.getvalue()
    assert "event=meal.started" in output
    assert 'trace="trace-1"' in output
    assert 'run="run-1"' in output
    assert 'attempt="attempt-1"' in output
    assert 'model="test-model"' in output


def test_json_event_is_flat_and_parseable():
    stream = _capture(log_format=LogFormat.JSON)
    with log_context(trace_id="trace-1"):
        log_event("meal.started", model="test-model", count=2)

    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    payload = json.loads(lines[0])
    assert payload["level"] == "INFO"
    assert payload["event"] == "meal.started"
    assert payload["trace_id"] == "trace-1"
    assert payload["model"] == "test-model"
    assert payload["count"] == 2
    assert "timestamp" in payload


def test_exception_log_includes_chained_cause_and_redacts_credentials():
    stream = _capture()

    try:
        try:
            raise ConnectionError("connect failed https://issuer.test/token?token=never-log")
        except ConnectionError as inner:
            raise RuntimeError("outer failure") from inner
    except RuntimeError as outer:
        log_exception("test.failed", outer)

    output = stream.getvalue()
    assert "RuntimeError" in output
    assert "ConnectionError" in output
    assert "direct cause" in output
    assert "issuer.test" not in output
    assert "never-log" not in output


def test_validation_error_is_summarized_outside_full_mode():
    class Payload(BaseModel):
        notes: str

    stream = _capture()
    try:
        Payload(notes=123)
    except ValidationError as exception:
        log_exception("test.validation", exception)

    output = stream.getvalue()
    assert "ValidationError" in output
    assert "notes" in output
    assert "string_type" in output
    assert "123" not in output
    assert "input_value" not in output


def test_validation_error_keeps_input_in_full_mode():
    class Payload(BaseModel):
        notes: str

    stream = _capture(DebugLevel.FULL)
    try:
        Payload(notes=123)
    except ValidationError as exception:
        log_exception("test.validation", exception)

    output = stream.getvalue()
    assert "ValidationError" in output
    assert "input_value" in output


def test_intercept_handler_routes_uvicorn_and_suppresses_third_party_debug():
    stream = _capture()
    configure_logging(
        DebugLevel.TRACE,
        sink=stream,
        log_format=LogFormat.TEXT,
        level="DEBUG",
        file_path=None,
        intercept_stdlib=True,
        force=True,
    )

    logging.getLogger("uvicorn.error").info("hello from uvicorn")
    logging.getLogger("httpx").debug("secret third-party debug")

    output = stream.getvalue()
    assert "hello from uvicorn" in output
    assert "uvicorn.error" in output
    assert "secret third-party debug" not in output


def test_file_sink_writes_rendered_events(tmp_path):
    stream = _capture()
    log_path = tmp_path / "nutriathena-agent.log"
    configure_logging(
        DebugLevel.TRACE,
        sink=stream,
        log_format=LogFormat.TEXT,
        level="DEBUG",
        file_path=str(log_path),
        force=True,
    )

    log_event("file.test", value=1)
    logger.complete()

    assert "event=file.test" in log_path.read_text(encoding="utf-8")


def test_oauth_failure_logs_full_cause_chain_without_url(monkeypatch):
    stream = _capture()
    settings = SimpleNamespace(
        token_url="https://issuer.test/token?token=never-log",
        oauth_client_id="client",
        oauth_client_secret="secret",
        mcp_scopes="scope.read",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "connect failed https://issuer.test/token?token=never-log",
            request=request,
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "nutriathena_agent.mcp_tools.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    with pytest.raises(McpSetupError) as captured:
        asyncio.run(
            connect_healthmind_mcp(
                settings,
                task_id=_TASK_ID,
                attempt_id=_ATTEMPT_ID,
            )
        )

    log_exception(
        "mcp.connect.failed",
        captured.value,
        stage=getattr(captured.value, "stage", None),
    )
    output = stream.getvalue()
    assert "McpSetupError" in output
    assert "ConnectError" in output
    assert "direct cause" in output
    assert 'stage="oauth"' in output
    assert "https://issuer.test" not in output
    assert "issuer.test/token" not in output
    assert "never-log" not in output
