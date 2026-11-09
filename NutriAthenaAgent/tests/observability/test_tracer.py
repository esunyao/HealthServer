from __future__ import annotations

import asyncio
import io
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from nutriathena_agent.observability import (
    DebugLevel, LogFormat, DebugTraceCallback, DebugTracer, configure_logging,
)


def _capture(level: DebugLevel) -> io.StringIO:
    stream = io.StringIO()
    configure_logging(
        level,
        sink=stream,
        log_format=LogFormat.TEXT,
        level="DEBUG",
        file_path=None,
        color="never",
        force=True,
    )
    return stream



def test_configure_logging_is_idempotent():
    stream = _capture(DebugLevel.TRACE)
    configure_logging(
        DebugLevel.TRACE,
        sink=stream,
        log_format=LogFormat.TEXT,
        level="DEBUG",
        file_path=None,
        color="never",
    )

    tracer = DebugTracer(DebugLevel.TRACE, trace_id="trace-test")
    tracer.event("llm.started", model="test-model")

    assert stream.getvalue().count("event=llm.started") == 1



def test_trace_level_never_emits_model_content():
    stream = _capture(DebugLevel.TRACE)
    tracer = DebugTracer(DebugLevel.TRACE, trace_id="trace-test", logger=None)

    tracer.event("llm.started", model="test-model", messages=1)
    tracer.content("llm.input[0]", "secret meal note")

    output = stream.getvalue()
    assert "event=llm.started" in output
    assert 'model="test-model"' in output
    assert "secret meal note" not in output
    assert "event=content" not in output



def test_full_level_redacts_images_urls_bearer_and_jwt():
    stream = _capture(DebugLevel.FULL)
    tracer = DebugTracer(DebugLevel.FULL, trace_id="trace-test")

    tracer.content(
        "llm.input",
        "note data:image/jpeg;base64,QUJD "
        "https://media.example.test/photo?token=secret "
        "Bearer abc.def "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123456",
    )

    output = stream.getvalue()
    assert "[data-url omitted]" in output
    assert "[URL removed]" in output
    assert "Bearer [redacted]" in output
    assert "[jwt removed]" in output
    assert "base64,QUJD" not in output
    assert "media.example.test" not in output
    assert "abc.def" not in output
    assert "signature123456" not in output



def test_full_level_redacts_sensitive_json_keys():
    stream = _capture(DebugLevel.FULL)
    tracer = DebugTracer(DebugLevel.FULL)

    tracer.content(
        "tool.output",
        '{"taskId":"11111111-1111-4111-8111-111111111111","access_token":"top-secret","items":[]}',
    )

    output = stream.getvalue()
    assert "taskId" in output
    assert "11111111-1111-4111-8111-111111111111" not in output
    assert "top-secret" not in output



def test_full_level_truncates_large_content():
    stream = _capture(DebugLevel.FULL)
    tracer = DebugTracer(DebugLevel.FULL)

    tracer.content("llm.output", "x" * (70 * 1024))

    assert "[truncated" in stream.getvalue()

