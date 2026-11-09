"""Domain redaction shared by structured fields, content blocks and exceptions."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

MAX_FIELD_CHARS = 64 * 1024

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

_ANSI_PATTERN = re.compile(
    r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))"
)
def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [truncated {len(text) - limit} chars]"


def redact_text(text: str, *, content: bool = False) -> str:
    """Remove credentials, URLs, terminal escapes and validation inputs."""
    redacted = _ANSI_PATTERN.sub("", text)
    redacted = _DATA_URL_PATTERN.sub("[data-url omitted]", redacted)
    redacted = _URL_PATTERN.sub("[URL removed]", redacted)
    redacted = _BEARER_PATTERN.sub("Bearer [redacted]", redacted)
    redacted = _JWT_PATTERN.sub("[jwt removed]", redacted)
    redacted = _JSON_SECRET_PATTERN.sub(r'\1"[redacted]"', redacted)
    redacted = _URI_CREDENTIAL_PATTERN.sub(r"\1[redacted]@", redacted)
    redacted = _SECRET_PARAM_PATTERN.sub(r"\1=[redacted]", redacted)
    if not content:
        redacted = _PYDANTIC_INPUT_PATTERN.sub("input_value=[redacted]", redacted)
    return redacted


def is_sensitive_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def safe_value(value: Any, *, content: bool) -> Any:
    if isinstance(value, Enum):
        return safe_value(value.value, content=content)
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted]" if is_sensitive_key(key) else safe_value(item, content=content)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [safe_value(item, content=content) for item in value]
    if isinstance(value, bytes):
        return f"[{len(value)} bytes]"
    if isinstance(value, str):
        return truncate(redact_text(value, content=content), MAX_FIELD_CHARS)
    if isinstance(value, BaseException):
        return truncate(redact_text(f"{type(value).__name__}: {value}", content=content), MAX_FIELD_CHARS)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return truncate(redact_text(str(value), content=content), MAX_FIELD_CHARS)


