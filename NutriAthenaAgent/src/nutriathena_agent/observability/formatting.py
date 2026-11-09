"""Prepare safe records once; let Loguru render color separately for each sink."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from .exceptions import render_exception
from .levels import LOG_COLOR_ENV, LogFormat
from .redaction import MAX_FIELD_CHARS, redact_text, safe_value, truncate

ENTRY_KEY = "_nutriathena_entry"
RENDER_KEY = "_nutriathena_render"
_REF = "extra[" + RENDER_KEY + "]"
_MAX_EVENT_CHARS = 256 * 1024
_CONTEXT_LABELS = (
    ("trace_id", "trace"),
    ("run_id", "run"),
    ("task_id", "task"),
    ("attempt_id", "attempt"),
)
_LEVEL_TAGS = {
    "TRACE": "<dim><white>",
    "DEBUG": "<cyan>",
    "INFO": "<green>",
    "SUCCESS": "<bold><green>",
    "WARNING": "<yellow>",
    "ERROR": "<red>",
    "CRITICAL": "<bold><red>",
}


def resolve_color(value: Any, sink: Any) -> bool:
    raw = str(value or "auto").strip().lower()
    if raw in {"always", "force", "true", "1", "yes", "on"}:
        return True
    if raw in {"never", "false", "0", "no", "off", "none"}:
        return False
    if raw not in {"auto", "tty", ""}:
        raise RuntimeError(f"运行配置 {LOG_COLOR_ENV} 必须是 auto、always 或 never")
    if "NO_COLOR" in os.environ:
        return False
    force = os.environ.get("FORCE_COLOR")
    if force is not None:
        return force.strip().lower() not in {"0", "false", "no", "off"}
    if getattr(sink, "isatty", lambda: False)():
        return True
    if sink is sys.stderr or sink is sys.stdout:
        pycharm = os.environ.get("PYCHARM_HOSTED", "").strip().lower()
        if pycharm and pycharm != "0":
            return True
        if "jetbrains" in os.environ.get("TERMINAL_EMULATOR", "").lower():
            return True
    return False


class RecordFormatter:
    def __init__(self, log_format: LogFormat, *, content: bool) -> None:
        self.log_format = log_format
        self.content = content

    def prepare(self, record: dict[str, Any]) -> None:
        """Redact before sink formatting; never use Loguru's exception renderer."""
        extra = record["extra"]
        entry = extra.pop(ENTRY_KEY, {})
        origin = entry.get("origin")
        if origin is not None:
            record["name"], record["function"], record["line"] = origin
        event = entry.get("event")
        if event is not None:
            event = redact_text(str(event), content=self.content)
        fields = {**extra, **entry.get("fields", {})}
        exception = entry.get("exception")
        if exception is None and record["exception"] is not None:
            exception = record["exception"].value
        exception_text = None
        message = record["message"]
        if exception is not None:
            exception_text, validation, chain, count = render_exception(
                exception,
                content=self.content,
            )
            fields.update(error_type=type(exception).__name__, error_chain=chain)
            if validation is not None:
                fields["validation_errors"] = validation
            if entry.get("default_exception_message"):
                message = (
                    f"{type(exception).__name__}: validation failed ({count} error(s))"
                    if validation is not None
                    else str(exception) or type(exception).__name__
                )
        record["exception"] = None
        record["message"] = truncate(
            redact_text(message, content=self.content), MAX_FIELD_CHARS
        )
        fields = {
            key: safe_value(
                value, content=self.content or (event == "content" and key == "text")
            )
            for key, value in fields.items()
        }
        snapshot = {
            "level": entry.get("level", record["level"].name),
            "event": event,
            "message": record["message"],
            "exception": exception_text,
            "fields": fields,
        }
        extra.update(fields)
        extra[RENDER_KEY] = snapshot
        if self.log_format is LogFormat.JSON:
            payload = {
                "timestamp": record["time"].isoformat(timespec="milliseconds"),
                "level": snapshot["level"],
                "logger": record["name"],
                "function": record["function"],
                "line": record["line"],
            }
            if event is not None:
                payload["event"] = event
            payload.update(fields)
            if record["message"]:
                payload["message"] = record["message"]
            if exception_text:
                payload["exception"] = exception_text
            snapshot["json"] = self._json_payload(payload)
        else:
            snapshot["template"] = self._text_template(record, snapshot)

    @staticmethod
    def _json_payload(payload: dict[str, Any]) -> str:
        # Bound the event without cutting JSON syntax in the middle of a value.
        parts: list[str] = []
        size = 2
        marker = '"truncated": true'
        for key, value in payload.items():
            item = (
                json.dumps(key, ensure_ascii=False)
                + ": "
                + json.dumps(value, ensure_ascii=False, default=str)
            )
            if size + len(item) + len(marker) + 4 > _MAX_EVENT_CHARS:
                parts.append(marker)
                break
            parts.append(item)
            size += len(item) + 2
        return "{" + ", ".join(parts) + "}"

    def _text_template(self, record: dict[str, Any], snapshot: dict[str, Any]) -> str:
        # Only trusted tags and placeholders enter the template. User text (including
        # braces/Loguru tags) always remains a record value.
        event = snapshot["event"]
        fields = dict(snapshot["fields"])
        body: list[str] | None = None
        if event == "content":
            label = fields.pop("label", "")
            text = str(fields.pop("text", ""))
            fields.update(label=label, chars=len(text))
            body = text.splitlines() or [""]
        segments: list[str] = []
        remaining = _MAX_EVENT_CHARS
        exhausted = False

        def fragment(text: str, tags: str = "") -> str:
            nonlocal remaining, exhausted
            if exhausted or not text:
                return ""
            if len(text) > remaining:
                text = truncate(text, remaining)
                exhausted = True
            remaining -= len(text)
            index = len(segments)
            segments.append(text)
            return tags + f"{{{_REF}[segments][{index}]}}" + ("</>" * tags.count("<"))

        def field(label: str, value: Any) -> str:
            return (
                fragment(label, "<dim>")
                + fragment("=")
                + fragment(json.dumps(value, ensure_ascii=False, default=str))
            )

        template = fragment(
            record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], "<dim>"
        )
        template += fragment(" | ") + fragment(
            f"{snapshot['level']:<8}", _LEVEL_TAGS.get(snapshot["level"], "")
        )
        template += fragment(" | ") + fragment(
            f"{record['name']}:{record['function']}:{record['line']}", "<cyan>"
        )
        context_started = False

        for key, label in _CONTEXT_LABELS:
            if key in fields:
                template += fragment(" " if context_started else " | ") + field(
                    label, fields.pop(key)
                )
                context_started = True
        if event is not None:
            template += fragment(" | ") + fragment(f"event={event}", "<bold><blue>")
        for key, value in fields.items():
            if exhausted:
                break
            template += fragment(" | ") + field(str(key), value)
        if snapshot["message"] and body is None:
            template += fragment(" " + snapshot["message"])
        if body is not None:
            for line in body:
                if exhausted:
                    break
                template += (
                    fragment("\n") + fragment("|", "<dim>") + fragment(" " + line)
                )
        elif snapshot["exception"]:
            template += fragment("\n" + snapshot["exception"])
        snapshot["segments"] = segments
        return template + "\n"

    def __call__(self, record: dict[str, Any]) -> str:
        if RENDER_KEY not in record["extra"]:
            self.prepare(record)
        snapshot = record["extra"][RENDER_KEY]
        if self.log_format is LogFormat.JSON:
            return f"{{{_REF}[json]}}\n"
        return snapshot["template"]
