"""Logging/debug levels and environment value parsers, independent of configuration."""

from __future__ import annotations

from enum import Enum

DEBUG_ENV = "NUTRIATHENA_DEBUG"
LOG_FORMAT_ENV = "NUTRIATHENA_LOG_FORMAT"
LOG_LEVEL_ENV = "NUTRIATHENA_LOG_LEVEL"
LOG_FILE_ENV = "NUTRIATHENA_LOG_FILE"
LOG_COLOR_ENV = "NUTRIATHENA_LOG_COLOR"

_OFF_VALUES = frozenset({"", "0", "false", "no", "none", "off"})
_TRACE_VALUES = frozenset({"1", "true", "yes", "on", "debug", "trace"})
_FULL_VALUES = frozenset({"full", "verbose", "content"})

_LOG_LEVELS = frozenset(
    {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
)
_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL"}


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
