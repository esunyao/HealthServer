from __future__ import annotations

import io
import json
import logging

import pytest
from pydantic import BaseModel, ValidationError

from nutriathena_agent.observability import (
    DebugLevel, configure_logging, log_context, log_exception, render_exception,
)


def _validation_error() -> ValidationError:
    class Payload(BaseModel):
        notes: int

    try:
        Payload(notes="private meal note https://media.example.test/x?token=secret")
    except ValidationError as exception:
        return exception
    raise AssertionError("Expected a validation error")


@pytest.mark.parametrize("link", ["cause", "context", "group"])
def test_validation_input_hidden_anywhere_in_exception_chain(link):
    validation = _validation_error()
    if link == "group":
        error = ExceptionGroup("private meal note", [RuntimeError("first"), validation])
    else:
        error = RuntimeError("private meal note")
        setattr(error, "__cause__" if link == "cause" else "__context__", validation)

    text, summary, chain, count = render_exception(error, content=False)

    assert "ValidationError" in chain
    assert "private meal note" not in text
    assert "media.example.test" not in text
    assert summary == [{"loc": "notes", "type": "int_parsing"}]
    assert count == 1


def test_cyclic_exception_chain_terminates_and_redacts_urls():
    outer = RuntimeError("outer https://example.test/?token=hidden")
    inner = ValueError("inner client_secret=hidden")
    outer.__cause__ = inner
    inner.__context__ = outer

    text, summary, chain, count = render_exception(outer, content=False)

    assert chain == "RuntimeError <- ValueError"
    assert "hidden" not in text
    assert "example.test" not in text
    assert summary is None
    assert count == 0


def test_full_validation_input_is_visible_but_credentials_are_redacted():
    text, summary, chain, count = render_exception(_validation_error(), content=True)

    assert "private meal note" in text
    assert "[URL removed]" in text
    assert "media.example.test" not in text
    assert summary is None
    assert chain == "ValidationError"
    assert count == 0


def test_exception_group_retains_safe_traceback_and_all_child_types():
    group = ExceptionGroup("synthetic group", [ValueError("a"), OSError("b")])

    text, summary, chain, count = render_exception(group, content=False)

    assert "ExceptionGroup" in chain
    assert "ValueError" in chain
    assert "OSError" in chain
    assert "ValueError: a" in text
    assert "OSError: b" in text
    assert summary is None
    assert count == 0


def test_stdlib_validation_exception_uses_safe_summary_and_context():
    stream = io.StringIO()
    configure_logging(
        sink=stream, log_format="json", file_path=None, color="never",
        intercept_stdlib=True, force=True,
    )
    error = _validation_error()
    with log_context(trace_id="trace"):
        logging.getLogger("uvicorn.error").error(
            "request failed", exc_info=(type(error), error, error.__traceback__),
        )

    event = json.loads(stream.getvalue())
    assert event["logger"] == "uvicorn.error"
    assert event["trace_id"] == "trace"
    assert event["error_type"] == "ValidationError"
    assert event["validation_errors"] == [{"loc": "notes", "type": "int_parsing"}]
    assert "input_value" not in event["exception"]
    assert "private meal note" not in stream.getvalue()


def test_json_exception_preserves_custom_message_and_valid_flat_object():
    stream = io.StringIO()
    configure_logging(DebugLevel.TRACE, sink=stream, log_format="json", file_path=None, color="never", force=True)
    log_exception("failed", RuntimeError("Bearer fake-token"), message="operation failed", stage="oauth")

    event = json.loads(stream.getvalue())
    assert event["event"] == "failed"
    assert event["message"] == "operation failed"
    assert event["error_type"] == "RuntimeError"
    assert event["stage"] == "oauth"
    assert "fake-token" not in event["exception"]
