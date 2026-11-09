"""Validated MCP context contracts, result decoding and model-facing sanitization."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from langchain_core.messages import ToolMessage
from mcp.types import CallToolResult
from pydantic import AnyUrl, BaseModel, ConfigDict, Field, ValidationError

MAX_CONTEXT_CHARS = 64 * 1024


_SENSITIVE_KEYS = {
    "access_token",
    "attempt_id",
    "authorization",
    "capture_session_id",
    "image_urls",
    "meal_id",
    "presigned_url",
    "subject_id",
    "task_id",
    "token",
    "trace_id",
    "url",
    "user_id",
}


_SENSITIVE_KEYS_NORMALIZED = {
    re.sub(r"[^a-z0-9]", "", key.lower()) for key in _SENSITIVE_KEYS
}


_SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "authorization",
    "credential",
    "password",
    "cookie",
    "apikey",
)


_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


class McpSetupError(RuntimeError):
    """The configured HealthMind MCP or OAuth client could not be initialized."""

    def __init__(self, message: str, *, stage: str = "mcp") -> None:
        super().__init__(message)
        self.stage = stage


class ConfirmedCaptureImage(BaseModel):
    """One authorized capture image from HealthMind's response contract."""

    model_config = ConfigDict(extra="forbid")

    content_type: str
    content_length: int = Field(ge=1)
    captured_at: datetime | None = None
    url: AnyUrl
    expires_in_seconds: int = Field(ge=1)


class CaptureContext(BaseModel):
    """Validated capture-context contract consumed by the meal runner."""

    model_config = ConfigDict(extra="forbid")

    capture_session_id: UUID
    meal_id: int
    meal_type: str
    consumed_at: datetime
    timezone: str
    notes: str | None = Field(default=None, max_length=1000)
    image_urls: list[ConfirmedCaptureImage] = Field(min_length=1)


def parse_capture_context(payload: dict[str, Any]) -> CaptureContext:
    try:
        return CaptureContext.model_validate(payload)
    except ValidationError as exception:
        raise McpSetupError(
            "HealthMind MCP capture context does not match the local contract",
            stage="capture_context",
        ) from exception


def _parse_mcp_json(result: Any) -> Any:
    if getattr(result, "isError", False) or (
        isinstance(result, dict) and result.get("isError")
    ):
        raise McpSetupError(
            "HealthMind MCP tool returned an error", stage="parse_context"
        )
    if isinstance(result, CallToolResult):
        if isinstance(result.structuredContent, dict):
            return result.structuredContent
        return _parse_mcp_json(result.content)
    if isinstance(result, ToolMessage):
        artifact = result.artifact
        if isinstance(artifact, dict):
            structured = artifact.get("structured_content")
            if isinstance(structured, dict):
                return structured
        return _parse_mcp_json(result.content)
    if isinstance(result, tuple) and len(result) == 2:
        content, artifact = result
        if isinstance(artifact, dict):
            structured = artifact.get("structured_content")
            if isinstance(structured, dict):
                return structured
        return _parse_mcp_json(content)
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    if isinstance(result, dict):
        if "structuredContent" in result:
            return result["structuredContent"]
        if "content" in result:
            return _parse_mcp_json(result["content"])
        return result
    if isinstance(result, list):
        texts = [
            item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
            for item in result
            if (isinstance(item, dict) and item.get("type") == "text")
            or getattr(item, "type", None) == "text"
        ]
        if len(texts) == 1 and isinstance(texts[0], str):
            return _parse_mcp_json(texts[0])
        if texts:
            return _parse_mcp_json("\n".join(texts))
        raise McpSetupError(
            "HealthMind MCP returned no JSON text", stage="parse_context"
        )
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError as exception:
            raise McpSetupError(
                "HealthMind MCP returned invalid JSON", stage="parse_context"
            ) from exception
    raise McpSetupError(
        "HealthMind MCP returned an unsupported response", stage="parse_context"
    )


def _remove_sensitive_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_sensitive_fields(item)
            for key, item in value.items()
            if not _is_sensitive_key(key)
        }
    if isinstance(value, list):
        return [_remove_sensitive_fields(item) for item in value]
    if isinstance(value, str):
        return _URL_PATTERN.sub("[URL removed]", value)
    return value


def _is_sensitive_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return (
        normalized in _SENSITIVE_KEYS_NORMALIZED
        or any(part in normalized for part in _SENSITIVE_KEY_PARTS)
        or normalized.endswith("url")
        or normalized.endswith("urls")
        or normalized.endswith("uri")
        or normalized.endswith("uris")
    )


def _context_json(result: Any, *, capture: bool) -> tuple[str, dict[str, Any]]:
    stage = "capture_context" if capture else "nutrition_context"
    payload = _parse_mcp_json(result)
    if not isinstance(payload, dict):
        raise McpSetupError("HealthMind MCP context must be a JSON object", stage=stage)
    raw_payload = payload
    if capture:
        parse_capture_context(payload)
    images = payload.get("image_urls")
    image_count = len(images) if isinstance(images, list) else 0
    safe_payload = _remove_sensitive_fields(payload)
    if capture:
        safe_payload["confirmed_image_count"] = image_count
    serialized = json.dumps(safe_payload, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > MAX_CONTEXT_CHARS:
        raise McpSetupError(
            "HealthMind MCP context exceeded the safe response size", stage=stage
        )
    return serialized, raw_payload
