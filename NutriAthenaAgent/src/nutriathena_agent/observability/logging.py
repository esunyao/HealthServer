"""Loguru sinks, context binding, lifecycle events and stdlib interception."""

from __future__ import annotations

import logging as stdlib_logging
import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from ..runtime.paths import MODULE_ROOT
from .formatting import ENTRY_KEY, RecordFormatter, resolve_color
from .levels import (
    LOG_COLOR_ENV,
    LOG_FILE_ENV,
    LOG_FORMAT_ENV,
    LOG_LEVEL_ENV,
    DebugLevel,
    LogFormat,
    parse_debug_level,
    parse_log_format,
    parse_log_level,
)

_UNSET = object()
_NOISY_LOGGERS = (
    "httpx", "httpcore", "mcp", "openai", "langchain", "langchain_core",
    "langgraph", "psycopg", "psycopg_pool", "urllib3",
)
_STDLIB_NAMES = ("", "uvicorn", "uvicorn.error", "uvicorn.asgi", "uvicorn.access", *_NOISY_LOGGERS)
_renderer = RecordFormatter(LogFormat.TEXT, content=False)
_configured = False
_handler_ids: list[int] = []
_default_handler_removed = False
_full_warning_emitted = False
_interception_saved: dict[str, tuple[list[stdlib_logging.Handler], int, bool]] | None = None


def _patch_record(record: dict[str, Any]) -> None:
    _renderer.prepare(record)


# A local patch leaves the application's global Loguru patcher untouched.
_logger = logger.patch(_patch_record)


def log_context(**values: Any) -> Any:
    """Bind nested trace/run/task/attempt fields, isolated across tasks and threads."""
    return logger.contextualize(**{key: value for key, value in values.items() if value not in (None, "")})


def log_event(event: str, *, level: str = "INFO", message: str = "", **fields: Any) -> None:
    try:
        entry = {"event": event, "fields": {key: value for key, value in fields.items() if value is not None}}
        _logger.bind(**{ENTRY_KEY: entry}).opt(depth=1).log(level, str(message or ""))
    except Exception:
        # Logging must never fail a meal run or the worker loop.
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
        entry = {
            "event": event,
            "exception": exception,
            "default_exception_message": message is None,
            "fields": {key: value for key, value in fields.items() if value is not None},
        }
        _logger.bind(**{ENTRY_KEY: entry}).opt(depth=1).log(level, str(message or ""))
    except Exception:
        pass


class InterceptHandler(stdlib_logging.Handler):
    """Route stdlib records through the same patch and renderer as application logs."""

    def emit(self, record: stdlib_logging.LogRecord) -> None:
        try:
            try:
                level: str | int = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            entry = {
                "origin": (record.name, record.funcName, record.lineno),
                "level": str(level),
                "exception": record.exc_info[1] if record.exc_info else None,
            }
            _logger.bind(**{ENTRY_KEY: entry}).opt(depth=1).log(level, record.getMessage())
        except Exception:
            pass


def _install_stdlib_interception() -> None:
    global _interception_saved
    if _interception_saved is not None:
        return
    _interception_saved = {}
    for name in _STDLIB_NAMES:
        target = stdlib_logging.getLogger(name)
        _interception_saved[name] = (list(target.handlers), target.level, target.propagate)
    root = stdlib_logging.getLogger()
    root.handlers = [InterceptHandler()]
    root.setLevel(stdlib_logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.asgi", "uvicorn.access"):
        target = stdlib_logging.getLogger(name)
        target.handlers = []
        target.propagate = name != "uvicorn.access"
        target.setLevel(stdlib_logging.INFO)
    for name in _NOISY_LOGGERS:
        stdlib_logging.getLogger(name).setLevel(stdlib_logging.WARNING)


def _restore_stdlib_interception() -> None:
    global _interception_saved
    if _interception_saved is not None:
        for name, (handlers, level, propagate) in _interception_saved.items():
            target = stdlib_logging.getLogger(name)
            target.handlers = handlers
            target.setLevel(level)
            target.propagate = propagate
    _interception_saved = None


def _remove_our_handlers() -> None:
    for handler_id in _handler_ids:
        try:
            logger.remove(handler_id)
        except ValueError:
            pass
    _handler_ids.clear()


def _enable_windows_console(stream: Any) -> Any:
    if sys.platform != "win32" or stream is not sys.stderr or sys.stderr is not sys.__stderr__:
        return stream
    try:
        from colorama import just_fix_windows_console

        just_fix_windows_console()
    except Exception:
        return stream
    return sys.stderr


def _resolve_file(value: Any) -> Path | None:
    if value is _UNSET:
        value = os.environ.get(LOG_FILE_ENV, "").strip()
    if value in (None, ""):
        return None
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else MODULE_ROOT / path


def configure_logging(
    debug_level: DebugLevel | str = DebugLevel.OFF,
    *,
    sink: Any = None,
    log_format: Any = _UNSET,
    level: Any = _UNSET,
    file_path: Any = _UNSET,
    color: Any = _UNSET,
    intercept_stdlib: bool = False,
    force: bool = False,
) -> None:
    """Install owned sinks idempotently, with color decided per sink by Loguru."""
    global _configured, _renderer, _default_handler_removed, _full_warning_emitted
    if _configured and not force:
        if intercept_stdlib:
            _install_stdlib_interception()
        return
    parsed_debug = parse_debug_level(debug_level)
    selected_format = parse_log_format(os.environ.get(LOG_FORMAT_ENV, "text") if log_format is _UNSET else log_format)
    selected_level = parse_log_level(os.environ.get(LOG_LEVEL_ENV, "INFO") if level is _UNSET else level)
    if parsed_debug is not DebugLevel.OFF:
        selected_level = "DEBUG"
    selected_file = _resolve_file(file_path)
    target_sink = sys.stderr if sink is None else sink
    requested_color = resolve_color(os.environ.get(LOG_COLOR_ENV, "auto") if color is _UNSET else color, target_sink)
    selected_color = selected_format is LogFormat.TEXT and requested_color
    if selected_color:
        target_sink = _enable_windows_console(target_sink)
    _remove_our_handlers()
    if not _default_handler_removed:
        _default_handler_removed = True
        try:
            logger.remove(0)
        except ValueError:
            pass
    _renderer = RecordFormatter(selected_format, content=parsed_debug is DebugLevel.FULL)
    sink_options = {
        "format": _renderer,
        "level": selected_level,
        "diagnose": False,
        "backtrace": False,
        "enqueue": False,
    }
    _handler_ids.append(logger.add(target_sink, colorize=selected_color, **sink_options))
    if selected_file is not None:
        try:
            selected_file.parent.mkdir(parents=True, exist_ok=True)
            _handler_ids.append(logger.add(
                str(selected_file), rotation="10 MB", retention="7 days",
                encoding="utf-8", colorize=False, **sink_options,
            ))
        except Exception as exception:
            log_event(
                "logging.file_sink.failed", level="WARNING",
                message=f"无法启用日志文件 {selected_file}: {type(exception).__name__}",
            )
    _configured = True
    if parsed_debug is DebugLevel.FULL and not _full_warning_emitted:
        _full_warning_emitted = True
        log_event(
            "logging.full_mode", level="WARNING",
            message="NUTRIATHENA_DEBUG=full：将输出模型输入输出与工具返回，仅限本地开发使用",
        )
    if intercept_stdlib:
        _install_stdlib_interception()


def reset_logging() -> None:
    """Remove only owned sinks and restore the stdlib state captured at install."""
    global _configured, _renderer, _full_warning_emitted
    _remove_our_handlers()
    _restore_stdlib_interception()
    _configured = False
    _renderer = RecordFormatter(LogFormat.TEXT, content=False)
    _full_warning_emitted = False
