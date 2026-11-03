"""Unified loguru-based logging for the NutriAthenaAgent runtime.

The service renders every event itself (text or JSON) and hands the finished
string to loguru.  Sinks therefore use the trivial ``{message}`` template: the
rendered string is never re-parsed as a format template, and exceptions are
formatted and redacted here instead of by loguru's unredacted traceback
renderer.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

from loguru import logger

DEBUG_ENV = "NUTRIATHENA_DEBUG"
LOG_FORMAT_ENV = "NUTRIATHENA_LOG_FORMAT"
LOG_LEVEL_ENV = "NUTRIATHENA_LOG_LEVEL"
LOG_FILE_ENV = "NUTRIATHENA_LOG_FILE"

_MODULE_ROOT = Path(__file__).resolve().parents[2]
_UNSET = object()

_MAX_FIELD_CHARS = 64 * 1024
_MAX_EVENT_CHARS = 256 * 1024
_MAX_EXCEPTION_CHARS = 64 * 1024
_MAX_VALIDATION_ERRORS = 20

_CONTEXT_LABELS = (
    ("trace_id", "trace"),
    ("run_id", "run"),
    ("task_id", "task"),
    ("attempt_id", "attempt"),
)

_OFF_VALUES = frozenset({"", "0", "false", "no", "none", "off"})
_TRACE_VALUES = frozenset({"1", "true", "yes", "on", "debug", "trace"})
_FULL_VALUES = frozenset({"full", "verbose", "content"})

_LOG_LEVELS = frozenset({"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"})
_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL"}

_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "mcp",
    "openai",
    "langchain",
    "langchain_core",
    "langgraph",
    "psycopg",
    "psycopg_pool",
    "urllib3",
)

_DATA_URL_PATTERN = re.compile(r"data:[^\s\"'<>]+", re.IGNORECASE)
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+\S+")
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_URI_CREDENTIAL_PATTERN = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^/\s@]+)@")
_SECRET_PARAM_PATTERN = re.compile(
    r"(?i)\b(password|passwd|client_secret|api[_-]?key|access_token|refresh_token|token)"
    r"=([^&\s\"'<>]+)"
)
_JSON_SECRET_PATTERN = re.compile(
    r'(?i)("(?:access_token|token|secret|authorization|password|cookie|api_?key|signature|'
    r'taskid|attemptid|capturesessionid|subjectid|userid)"\s*:\s*)"(?:[^"\\]|\\.)*"'
)
_PYDANTIC_INPUT_PATTERN = re.compile(r"input_value=.*?(?=,\s*input_type=|\n|$)", re.DOTALL)
_SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "authorization",
    "credential",
    "password",
    "cookie",
    "apikey",
    "signature",
)


class DebugLevel(str, Enum):
    OFF = "off"
    TRACE = "trace"
    FULL = "full"


class LogFormat(str, Enum):
    TEXT = "text"
    JSON = "json"


def parse_debug_level(value: str | DebugLevel | None) -> DebugLevel:
    if isinstance(value, DebugLevel):
        return value
    raw = (value or "").strip().lower()
    if raw in _OFF_VALUES:
        return DebugLevel.OFF
    if raw in _TRACE_VALUES:
        return DebugLevel.TRACE
    if raw in _FULL_VALUES:
        return DebugLevel.FULL
    raise RuntimeError("运行配置 NUTRIATHENA_DEBUG 必须是 off、trace 或 full")


def parse_log_format(value: str | LogFormat | None) -> LogFormat:
    if isinstance(value, LogFormat):
        return value
    raw = (value or "text").strip().lower()
    if raw in {"", "text", "plain", "console"}:
        return LogFormat.TEXT
    if raw in {"json", "jsonl", "ndjson"}:
        return LogFormat.JSON
    raise RuntimeError("运行配置 NUTRIATHENA_LOG_FORMAT 必须是 text 或 json")


def parse_log_level(value: str | None) -> str:
    raw = (value or "INFO").strip().upper()
    raw = _LEVEL_ALIASES.get(raw, raw)
    if raw not in _LOG_LEVELS:
        allowed = "、".join(sorted(_LOG_LEVELS))
        raise RuntimeError(f"运行配置 NUTRIATHENA_LOG_LEVEL 必须是 {allowed}")
    return raw


_context: ContextVar[dict[str, Any] | None] = ContextVar("nutriathena_log_context", default=None)
_log_format = LogFormat.TEXT
_content_mode = False
_configured = False
_handler_ids: list[int] = []
_default_handler_removed = False
_full_warning_emitted = False
_interception_installed = False
_interception_saved: dict[str, Any] | None = None


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [truncated {len(text) - limit} chars]"


def redact_text(text: str, *, content: bool = False) -> str:
    """Remove credentials, URLs and (outside full mode) validation inputs."""
    redacted = _DATA_URL_PATTERN.sub("[data-url omitted]", text)
    redacted = _URL_PATTERN.sub("[URL removed]", redacted)
    redacted = _BEARER_PATTERN.sub("Bearer [redacted]", redacted)
    redacted = _JWT_PATTERN.sub("[jwt removed]", redacted)
    redacted = _JSON_SECRET_PATTERN.sub(r'\1"[redacted]"', redacted)
    redacted = _URI_CREDENTIAL_PATTERN.sub(r"\1[redacted]@", redacted)
    redacted = _SECRET_PARAM_PATTERN.sub(r"\1=[redacted]", redacted)
    if not content:
        redacted = _PYDANTIC_INPUT_PATTERN.sub("input_value=[redacted]", redacted)
    return redacted


def _is_sensitive_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _plain(value: Any, *, content: bool) -> Any:
    if isinstance(value, Enum):
        return _plain(value.value, content=content)
    if isinstance(value, dict):
        return {
            str(key): ("[redacted]" if _is_sensitive_key(key) else _plain(item, content=content))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(item, content=content) for item in value]
    if isinstance(value, bytes):
        return f"[{len(value)} bytes]"
    if isinstance(value, str):
        return _truncate(redact_text(value, content=content), _MAX_FIELD_CHARS)
    if isinstance(value, BaseException):
        return _truncate(
            redact_text(f"{type(value).__name__}: {value}", content=content),
            _MAX_FIELD_CHARS,
        )
    return value


def _format_value(value: Any, *, content: bool) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(_truncate(redact_text(value, content=content), _MAX_FIELD_CHARS), ensure_ascii=False)
    if isinstance(value, (dict, list, tuple, set, frozenset)):
        return json.dumps(_plain(value, content=content), ensure_ascii=False, default=str)
    if isinstance(value, BaseException):
        return json.dumps(
            _truncate(redact_text(f"{type(value).__name__}: {value}", content=content), _MAX_FIELD_CHARS),
            ensure_ascii=False,
        )
    return json.dumps(str(_plain(value, content=content)), ensure_ascii=False, default=str)


def _json_safe(value: Any, *, content: bool) -> Any:
    if isinstance(value, Enum):
        return _json_safe(value.value, content=content)
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted]" if _is_sensitive_key(key) else _json_safe(item, content=content)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item, content=content) for item in value]
    if isinstance(value, bytes):
        return f"[{len(value)} bytes]"
    if isinstance(value, str):
        return _truncate(redact_text(value, content=content), _MAX_FIELD_CHARS)
    if isinstance(value, BaseException):
        return _truncate(redact_text(f"{type(value).__name__}: {value}", content=content), _MAX_FIELD_CHARS)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _iter_exception_chain(exception: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    stack: list[BaseException] = [exception]
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        nested = getattr(current, "exceptions", None)
        if isinstance(nested, (list, tuple)):
            stack.extend(item for item in nested if isinstance(item, BaseException))
        if current.__cause__ is not None:
            stack.append(current.__cause__)
        if current.__context__ is not None:
            stack.append(current.__context__)


def _is_validation_error(exception: BaseException) -> bool:
    return type(exception).__name__ == "ValidationError" and callable(getattr(exception, "errors", None))


def _validation_errors(exception: BaseException) -> list[dict[str, str]]:
    try:
        errors = exception.errors(  # type: ignore[attr-defined]
            include_input=False,
            include_url=False,
            include_context=False,
        )
    except TypeError:
        try:
            errors = exception.errors(include_input=False, include_url=False)  # type: ignore[attr-defined]
        except Exception:
            return []
    except Exception:
        return []
    if not isinstance(errors, list):
        return []
    summary: list[dict[str, str]] = []
    for item in errors[:_MAX_VALIDATION_ERRORS]:
        if not isinstance(item, dict):
            continue
        location = item.get("loc") or ()
        summary.append(
            {
                "loc": ".".join(str(part) for part in location),
                "type": str(item.get("type", "unknown")),
            }
        )
    return summary


def render_exception(
    exception: BaseException,
    *,
    content: bool,
) -> tuple[str, list[dict[str, str]] | None, str, int]:
    """Render an exception chain without leaking validation inputs.

    Returns ``(exception_text, validation_errors, error_chain, error_count)``.
    """
    chain = list(_iter_exception_chain(exception))
    error_chain = " <- ".join(type(item).__name__ for item in chain)
    validation = next((item for item in chain if _is_validation_error(item)), None)
    if validation is not None and not content:
        errors = _validation_errors(validation)
        total = len(errors)
        text = f"{error_chain}: {total} validation error(s)"
        return text, errors, error_chain, total
    try:
        text = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    except Exception:
        text = f"{type(exception).__name__}: {exception}"
    text = _truncate(redact_text(text, content=content), _MAX_EXCEPTION_CHARS)
    return text, None, error_chain, 0


def log_context(**values: Any) -> Any:
    """Context manager binding trace/run/task/attempt IDs for nested logs."""
    cleaned = {key: value for key, value in values.items() if value not in (None, "")}
    return _context_scope(cleaned)


@contextmanager
def _context_scope(values: dict[str, Any]) -> Iterator[None]:
    current = dict(_context.get() or {})
    current.update(values)
    token = _context.set(current)
    try:
        yield
    finally:
        _context.reset(token)


def _caller_info() -> tuple[str, str, int]:
    try:
        frame = sys._getframe(2)
    except ValueError:
        return "unknown", "unknown", 0
    return (
        str(frame.f_globals.get("__name__", "unknown")),
        frame.f_code.co_name,
        frame.f_lineno,
    )


def _timestamp_text() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _timestamp_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _render_text(
    *,
    level: str,
    name: str,
    function: str,
    line: int,
    event: str | None,
    fields: dict[str, Any],
    message: str,
    exception_text: str | None,
) -> str:
    content = _content_mode
    values = dict(fields)
    parts = [_timestamp_text(), f"{level:<8}", f"{name}:{function}:{line}"]
    context_parts: list[str] = []
    for key, label in _CONTEXT_LABELS:
        if key in values:
            context_parts.append(f"{label}={_format_value(values.pop(key), content=content)}")
    if context_parts:
        parts.append(" ".join(context_parts))
    if event is not None:
        parts.append(f"event={event}")
    for key, value in values.items():
        if key == "text" and event == "content":
            continue
        parts.append(f"{key}={_format_value(value, content=content)}")
    rendered = " | ".join(parts)
    if message:
        rendered += " " + _truncate(redact_text(message, content=content), _MAX_FIELD_CHARS)
    if exception_text:
        rendered += "\n" + exception_text
    return _truncate(rendered, _MAX_EVENT_CHARS)


_CONTEXT_KEYS = frozenset(key for key, _ in _CONTEXT_LABELS)


def _render_json(
    *,
    level: str,
    name: str,
    function: str,
    line: int,
    event: str | None,
    fields: dict[str, Any],
    message: str,
    exception_text: str | None,
) -> str:
    content = _content_mode
    payload: dict[str, Any] = {
        "timestamp": _timestamp_iso(),
        "level": level,
        "logger": name,
        "function": function,
        "line": line,
    }
    if event is not None:
        payload["event"] = event
    for key in _CONTEXT_KEYS:
        if key in fields:
            payload[key] = _json_safe(fields[key], content=content)
    for key, value in fields.items():
        if key in _CONTEXT_KEYS:
            continue
        payload[key] = _json_safe(value, content=content)
    if message:
        payload["message"] = _truncate(redact_text(message, content=content), _MAX_FIELD_CHARS)
    if exception_text:
        payload["exception"] = exception_text
    return _truncate(json.dumps(payload, ensure_ascii=False, default=str), _MAX_EVENT_CHARS)


def _render_content_block(
    *,
    level: str,
    name: str,
    function: str,
    line: int,
    fields: dict[str, Any],
) -> str:
    values = dict(fields)
    label = values.pop("label", "")
    text = _truncate(redact_text(str(values.pop("text", "")), content=True), _MAX_FIELD_CHARS)
    header = _render_text(
        level=level,
        name=name,
        function=function,
        line=line,
        event="content",
        fields={**values, "label": label, "chars": len(text)},
        message="",
        exception_text=None,
    )
    lines = text.splitlines() or [""]
    return _truncate(header + "\n" + "\n".join(f"| {item}" for item in lines), _MAX_EVENT_CHARS)


def _render(
    *,
    level: str,
    name: str,
    function: str,
    line: int,
    event: str | None,
    fields: dict[str, Any],
    message: str,
    exception_text: str | None = None,
) -> str:
    if _log_format is LogFormat.JSON:
        return _render_json(
            level=level,
            name=name,
            function=function,
            line=line,
            event=event,
            fields=fields,
            message=message,
            exception_text=exception_text,
        )
    if event == "content":
        return _render_content_block(
            level=level,
            name=name,
            function=function,
            line=line,
            fields=fields,
        )
    return _render_text(
        level=level,
        name=name,
        function=function,
        line=line,
        event=event,
        fields=fields,
        message=message,
        exception_text=exception_text,
    )


def log_event(event: str, *, level: str = "INFO", message: str = "", **fields: Any) -> None:
    try:
        merged = {**(_context.get() or {}), **{key: value for key, value in fields.items() if value is not None}}
        name, function, line = _caller_info()
        rendered = _render(
            level=str(level),
            name=name,
            function=function,
            line=line,
            event=event,
            fields=merged,
            message=str(message or ""),
        )
        logger.log(level, rendered)
    except Exception:
        # Logging must never break the meal run or worker loop.
        pass


def log_exception(
    event: str,
    exception: BaseException,
    *,
    level: str = "ERROR",
    message: str | None = None,
    **fields: Any,
) -> None:
    try:
        exception_text, validation_errors, error_chain, error_count = render_exception(
            exception,
            content=_content_mode,
        )
        if message is None:
            if validation_errors is not None and not _content_mode:
                message = f"{type(exception).__name__}: validation failed ({error_count} error(s))"
            else:
                message = str(exception) or type(exception).__name__
        merged: dict[str, Any] = {
            **(_context.get() or {}),
            **{key: value for key, value in fields.items() if value is not None},
            "error_type": type(exception).__name__,
            "error_chain": error_chain,
        }
        if validation_errors is not None:
            merged["validation_errors"] = validation_errors
        name, function, line = _caller_info()
        rendered = _render(
            level=str(level),
            name=name,
            function=function,
            line=line,
            event=event,
            fields=merged,
            message=str(message),
            exception_text=exception_text,
        )
        logger.log(level, rendered)
    except Exception:
        pass


class InterceptHandler(logging.Handler):
    """Route stdlib logging records through the same safe renderer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            try:
                level: str | int = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            message = record.getMessage()
            exception_text = None
            extra: dict[str, Any] = {}
            if record.exc_info and record.exc_info[1] is not None:
                exception_value = record.exc_info[1]
                exception_text, validation_errors, error_chain, _ = render_exception(
                    exception_value,
                    content=_content_mode,
                )
                extra["error_type"] = type(exception_value).__name__
                extra["error_chain"] = error_chain
                if validation_errors is not None:
                    extra["validation_errors"] = validation_errors
            merged = {**(_context.get() or {}), **extra}
            rendered = _render(
                level=str(level),
                name=record.name,
                function=record.funcName,
                line=record.lineno,
                event=None,
                fields=merged,
                message=message,
                exception_text=exception_text,
            )
            logger.log(level, rendered)
        except Exception:
            pass


def _resolve_format(value: Any) -> LogFormat:
    if value is _UNSET:
        value = os.environ.get(LOG_FORMAT_ENV, "text")
    return parse_log_format(value)


def _resolve_level(value: Any, debug_level: DebugLevel) -> str:
    if value is _UNSET:
        value = os.environ.get(LOG_LEVEL_ENV, "INFO")
    selected = parse_log_level(value)
    return "DEBUG" if debug_level is not DebugLevel.OFF else selected


def _resolve_file(value: Any) -> Path | None:
    if value is _UNSET:
        value = os.environ.get(LOG_FILE_ENV, "").strip()
    if value in (None, ""):
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = _MODULE_ROOT / path
    return path


def _remove_our_handlers() -> None:
    for handler_id in list(_handler_ids):
        try:
            logger.remove(handler_id)
        except ValueError:
            pass
    _handler_ids.clear()


def _remove_default_handler_once() -> None:
    global _default_handler_removed
    if _default_handler_removed:
        return
    _default_handler_removed = True
    try:
        logger.remove(0)
    except ValueError:
        pass


def _save_logger_state(name: str) -> tuple[list[logging.Handler], int, bool]:
    target = logging.getLogger(name)
    return list(target.handlers), target.level, target.propagate


def _restore_logger_state(
    name: str,
    state: tuple[list[logging.Handler], int, bool],
) -> None:
    target = logging.getLogger(name)
    target.handlers = state[0]
    target.setLevel(state[1])
    target.propagate = state[2]


def _install_stdlib_interception() -> None:
    global _interception_installed, _interception_saved
    if _interception_installed:
        return
    names = ("uvicorn", "uvicorn.error", "uvicorn.asgi", "uvicorn.access", *_NOISY_LOGGERS)
    _interception_saved = {
        "root": _save_logger_state(""),
        "loggers": {name: _save_logger_state(name) for name in names},
    }
    root = logging.getLogger()
    root.handlers = [InterceptHandler()]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.asgi"):
        target = logging.getLogger(name)
        target.handlers = []
        target.propagate = True
        target.setLevel(logging.INFO)
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.setLevel(logging.INFO)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    _interception_installed = True


def _restore_stdlib_interception() -> None:
    global _interception_installed, _interception_saved
    saved = _interception_saved
    if saved is not None:
        _restore_logger_state("", saved["root"])
        for name, state in saved["loggers"].items():
            _restore_logger_state(name, state)
    _interception_saved = None
    _interception_installed = False


def configure_logging(
    debug_level: DebugLevel | str = DebugLevel.OFF,
    *,
    sink: Any = None,
    log_format: Any = _UNSET,
    level: Any = _UNSET,
    file_path: Any = _UNSET,
    intercept_stdlib: bool = False,
    force: bool = False,
) -> None:
    """Install the process-wide loguru sink(s) idempotently."""
    global _configured, _log_format, _content_mode, _full_warning_emitted

    if _configured and not force:
        if intercept_stdlib:
            _install_stdlib_interception()
        return

    parsed_debug = parse_debug_level(debug_level)
    selected_format = _resolve_format(log_format)
    selected_level = _resolve_level(level, parsed_debug)
    selected_file = _resolve_file(file_path)

    _log_format = selected_format
    _content_mode = parsed_debug is DebugLevel.FULL
    _remove_our_handlers()
    _remove_default_handler_once()

    target_sink = sys.stderr if sink is None else sink
    _handler_ids.append(
        logger.add(
            target_sink,
            format="{message}",
            level=selected_level,
            colorize=False,
            diagnose=False,
            backtrace=False,
            enqueue=False,
        )
    )
    if selected_file is not None:
        try:
            selected_file.parent.mkdir(parents=True, exist_ok=True)
            _handler_ids.append(
                logger.add(
                    str(selected_file),
                    format="{message}",
                    level=selected_level,
                    rotation="10 MB",
                    retention="7 days",
                    encoding="utf-8",
                    colorize=False,
                    diagnose=False,
                    backtrace=False,
                    enqueue=False,
                )
            )
        except Exception as exception:
            log_event(
                "logging.file_sink.failed",
                level="WARNING",
                message=f"无法启用日志文件 {selected_file}: {type(exception).__name__}",
            )

    _configured = True
    if parsed_debug is DebugLevel.FULL and not _full_warning_emitted:
        _full_warning_emitted = True
        log_event(
            "logging.full_mode",
            level="WARNING",
            message="NUTRIATHENA_DEBUG=full：将输出模型输入输出与工具返回，仅限本地开发使用",
        )
    if intercept_stdlib:
        _install_stdlib_interception()


def reset_logging() -> None:
    """Remove handlers installed by this service and restore stdlib state."""
    global _configured, _log_format, _content_mode, _full_warning_emitted
    _remove_our_handlers()
    _restore_stdlib_interception()
    _configured = False
    _log_format = LogFormat.TEXT
    _content_mode = False
    _full_warning_emitted = False
