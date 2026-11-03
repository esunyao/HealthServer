from __future__ import annotations

import asyncio
import io
import logging
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from nutriathena_agent import main as cli
from nutriathena_agent.config import load_meal_settings
from nutriathena_agent.debug import (
    DEBUG_LOGGER_NAME,
    DebugLevel,
    DebugTraceCallback,
    DebugTracer,
    configure_debug_logging,
    parse_debug_level,
)
from nutriathena_agent.runtime_config import load_runtime_settings

_TASK_ID = "11111111-1111-4111-8111-111111111111"
_ATTEMPT_ID = "22222222-2222-4222-8222-222222222222"

_RUNTIME_ENV = {
    "NUTRIATHENA_DATABASE_URL": "postgresql://unused",
    "NUTRIATHENA_OAUTH_ISSUER": "https://issuer.example.test/",
    "NUTRIATHENA_OAUTH_JWKS_URL": "https://issuer.example.test/jwks/",
    "NUTRIATHENA_RELEASE_ID": "33333333-3333-4333-8333-333333333333",
    "NUTRIATHENA_DEPLOYMENT_KEY": "meal-analysis-test",
    "NUTRIATHENA_ASSISTANT_ID": "nutriathena-meal-test",
}

_MEAL_ENV = {
    "NUTRIATHENA_MEAL_MODEL_ID": "vision-test",
    "NUTRIATHENA_MODEL_API_KEY": "test-key",
    "NUTRIATHENA_MODEL_BASE_URL": "https://example.invalid/v1",
    "NUTRIATHENA_MCP_URL": "https://mcp.example.invalid/mcp",
    "NUTRIATHENA_MCP_OAUTH_TOKEN_URL": "https://issuer.example.invalid/token",
    "NUTRIATHENA_MCP_CLIENT_ID": "test-client",
    "NUTRIATHENA_MCP_CLIENT_SECRET": "test-secret",
}


def _capture_logger() -> tuple[logging.Logger, io.StringIO]:
    logger = logging.getLogger(f"test.debug.{uuid4()}")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger, stream


@pytest.mark.parametrize("value", ["", None, "off", "0", "false", "no", "none", " OFF "])
def test_parse_debug_level_off(value):
    assert parse_debug_level(value) is DebugLevel.OFF


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "debug", "trace", " TRACE "])
def test_parse_debug_level_trace(value):
    assert parse_debug_level(value) is DebugLevel.TRACE


@pytest.mark.parametrize("value", ["full", "verbose", "content", " FULL "])
def test_parse_debug_level_full(value):
    assert parse_debug_level(value) is DebugLevel.FULL


def test_parse_debug_level_rejects_unknown_values():
    with pytest.raises(RuntimeError, match="NUTRIATHENA_DEBUG"):
        parse_debug_level("loud")


def test_runtime_settings_reads_debug_level(monkeypatch):
    for name, value in _RUNTIME_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("NUTRIATHENA_DEBUG", "full")

    assert load_runtime_settings().debug_level is DebugLevel.FULL


def test_meal_settings_default_and_override_debug_level(monkeypatch):
    for name, value in _MEAL_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("NUTRIATHENA_DEBUG", "off")
    assert load_meal_settings().debug_level is DebugLevel.OFF

    monkeypatch.setenv("NUTRIATHENA_DEBUG", "trace")
    assert load_meal_settings().debug_level is DebugLevel.TRACE


def test_configure_debug_logging_is_idempotent_and_off_removes_handler():
    logger = logging.getLogger(DEBUG_LOGGER_NAME)
    try:
        configure_debug_logging(DebugLevel.TRACE)
        first = [handler for handler in logger.handlers if getattr(handler, "_nutriathena_debug_handler", False)]
        assert len(first) == 1
        assert logger.propagate is False

        configure_debug_logging(DebugLevel.TRACE)
        second = [handler for handler in logger.handlers if getattr(handler, "_nutriathena_debug_handler", False)]
        assert len(second) == 1

        configure_debug_logging(DebugLevel.OFF)
        remaining = [handler for handler in logger.handlers if getattr(handler, "_nutriathena_debug_handler", False)]
        assert remaining == []
        assert logger.propagate is True
    finally:
        configure_debug_logging(DebugLevel.OFF)


def test_trace_level_never_emits_model_content():
    logger, stream = _capture_logger()
    tracer = DebugTracer(DebugLevel.TRACE, trace_id="trace-test", logger=logger)

    tracer.event("llm.started", model="test-model", messages=1)
    tracer.content("llm.input[0]", "secret meal note")

    output = stream.getvalue()
    assert "event=llm.started" in output
    assert 'model="test-model"' in output
    assert "secret meal note" not in output
    assert "event=content" not in output


def test_full_level_redacts_images_urls_bearer_and_jwt():
    logger, stream = _capture_logger()
    tracer = DebugTracer(DebugLevel.FULL, trace_id="trace-test", logger=logger)

    tracer.content(
        "llm.input",
        "note data:image/jpeg;base64,QUJD "
        "https://media.example.test/photo?token=secret "
        "Bearer abc.def "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123456",
    )

    output = stream.getvalue()
    assert "[data-url removed]" in output
    assert "[URL removed]" in output
    assert "Bearer [redacted]" in output
    assert "[jwt removed]" in output
    assert "base64,QUJD" not in output
    assert "media.example.test" not in output
    assert "abc.def" not in output
    assert "signature123456" not in output


def test_full_level_redacts_sensitive_json_keys():
    logger, stream = _capture_logger()
    tracer = DebugTracer(DebugLevel.FULL, logger=logger)

    tracer.content(
        "tool.output",
        '{"taskId":"11111111-1111-4111-8111-111111111111","access_token":"top-secret","items":[]}',
    )

    output = stream.getvalue()
    assert r'\"taskId\":\"[redacted]\"' in output
    assert r'\"access_token\":\"[redacted]\"' in output
    assert "top-secret" not in output
    assert "11111111-1111-4111-8111-111111111111" not in output


def test_full_level_truncates_large_content():
    logger, stream = _capture_logger()
    tracer = DebugTracer(DebugLevel.FULL, logger=logger)

    tracer.content("llm.output", "x" * (70 * 1024))

    assert "[truncated" in stream.getvalue()


def test_callback_trace_level_records_structure_without_content():
    logger, stream = _capture_logger()
    tracer = DebugTracer(DebugLevel.TRACE, trace_id="trace-test", logger=logger)
    callback = DebugTraceCallback(tracer)
    run_id = uuid4()
    messages = [
        [
            HumanMessage(
                content=[
                    {"type": "text", "text": "secret meal note"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}},
                ]
            )
        ]
    ]
    response = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content='{"items":[{"name":"米饭"}]}'))]],
        llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
    )

    asyncio.run(callback.on_chat_model_start({}, messages, run_id=run_id))
    asyncio.run(callback.on_llm_end(response, run_id=run_id))

    output = stream.getvalue()
    assert "event=llm.started" in output
    assert "image_parts=1" in output
    assert "event=llm.finished" in output
    assert "prompt_tokens=10" in output
    assert "completion_tokens=5" in output
    assert "total_tokens=15" in output
    assert "secret meal note" not in output
    assert "米饭" not in output
    assert "base64,QUJD" not in output


def test_callback_full_level_redacts_content():
    logger, stream = _capture_logger()
    tracer = DebugTracer(DebugLevel.FULL, trace_id="trace-test", logger=logger)
    callback = DebugTraceCallback(tracer)
    run_id = uuid4()
    messages = [
        [
            HumanMessage(
                content=[
                    {"type": "text", "text": "secret meal note"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}},
                ]
            )
        ]
    ]
    response = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content='{"items":[{"name":"米饭"}]}'))]],
        llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}},
    )

    asyncio.run(callback.on_chat_model_start({}, messages, run_id=run_id))
    asyncio.run(callback.on_llm_end(response, run_id=run_id))

    output = stream.getvalue()
    assert "secret meal note" in output
    assert "米饭" in output
    assert "[image omitted: image/jpeg]" in output
    assert "base64,QUJD" not in output


def test_callback_chain_events_only_for_langgraph_nodes():
    logger, stream = _capture_logger()
    tracer = DebugTracer(DebugLevel.TRACE, logger=logger)
    callback = DebugTraceCallback(tracer)
    node_run = uuid4()
    child_run = uuid4()

    asyncio.run(
        callback.on_chain_start(
            {},
            {},
            run_id=node_run,
            metadata={"langgraph_node": "model"},
            name="model",
        )
    )
    asyncio.run(
        callback.on_chain_start(
            {},
            {},
            run_id=child_run,
            metadata={"langgraph_node": "model"},
            name="RunnableSequence",
        )
    )
    asyncio.run(callback.on_chain_end({}, run_id=child_run))
    asyncio.run(callback.on_chain_end({}, run_id=node_run))

    output = stream.getvalue()
    assert output.count("event=node.started") == 1
    assert output.count("event=node.finished") == 1


def test_callback_tool_events_record_duration_and_redact_output():
    logger, stream = _capture_logger()
    tracer = DebugTracer(DebugLevel.FULL, logger=logger)
    callback = DebugTraceCallback(tracer)
    run_id = uuid4()

    asyncio.run(callback.on_tool_start({"name": "capture_context"}, "{}", run_id=run_id))
    asyncio.run(callback.on_tool_end("https://media.example.test/x?token=secret", run_id=run_id))

    output = stream.getvalue()
    assert "event=tool.started" in output
    assert 'tool="capture_context"' in output
    assert "event=tool.finished" in output
    assert "duration_ms=" in output
    assert "[URL removed]" in output
    assert "token=secret" not in output


def test_callback_tool_error_only_records_type_at_trace_level():
    logger, stream = _capture_logger()
    tracer = DebugTracer(DebugLevel.TRACE, logger=logger)
    callback = DebugTraceCallback(tracer)
    run_id = uuid4()

    asyncio.run(callback.on_tool_start({"name": "nutrition_context"}, "{}", run_id=run_id))
    asyncio.run(callback.on_tool_error(RuntimeError("secret https://x.test"), run_id=run_id))

    output = stream.getvalue()
    assert "event=tool.error" in output
    assert 'error_type="RuntimeError"' in output
    assert "secret" not in output
    assert "x.test" not in output


def _fake_meal(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_run(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr("nutriathena_agent.meal_agent.run_meal_analysis", fake_run)
    return captured


def test_meal_cli_debug_full_sets_environment(monkeypatch):
    monkeypatch.delenv("NUTRIATHENA_DEBUG", raising=False)
    _fake_meal(monkeypatch)

    code = cli.main(["meal", "--debug", "full", "--task-id", _TASK_ID, "--attempt-id", _ATTEMPT_ID])

    assert code == 0
    assert os.environ["NUTRIATHENA_DEBUG"] == "full"


def test_meal_cli_debug_off_overrides_environment(monkeypatch):
    monkeypatch.setenv("NUTRIATHENA_DEBUG", "trace")
    _fake_meal(monkeypatch)

    code = cli.main(["meal", "--debug", "off", "--task-id", _TASK_ID, "--attempt-id", _ATTEMPT_ID])

    assert code == 0
    assert os.environ["NUTRIATHENA_DEBUG"] == "off"


def test_meal_cli_without_debug_keeps_environment(monkeypatch):
    monkeypatch.setenv("NUTRIATHENA_DEBUG", "trace")
    _fake_meal(monkeypatch)

    code = cli.main(["meal", "--task-id", _TASK_ID, "--attempt-id", _ATTEMPT_ID])

    assert code == 0
    assert os.environ["NUTRIATHENA_DEBUG"] == "trace"


def test_serve_cli_debug_argument_is_applied_from_parser(monkeypatch):
    monkeypatch.delenv("NUTRIATHENA_DEBUG", raising=False)
    args = cli.build_parser().parse_args(["serve", "--debug", "trace"])

    cli._apply_debug_argument(SimpleNamespace(**vars(args)))

    assert os.environ["NUTRIATHENA_DEBUG"] == "trace"
