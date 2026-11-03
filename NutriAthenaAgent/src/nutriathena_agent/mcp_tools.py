"""Read-only HealthMind MCP tools bound to one task and attempt."""

from __future__ import annotations

import json
import re
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import urlsplit
from uuid import UUID, uuid5

import httpx
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, tool
from pydantic import AnyUrl, BaseModel, ConfigDict, Field, ValidationError

from .config import MealSettings
from .logging_service import log_event, log_exception

CAPTURE_CONTEXT_TOOL = "nutrimemo.capture_context.get"
NUTRITION_CONTEXT_TOOL = "orion.nutrition_context.get"
MAX_CONTEXT_CHARS = 64 * 1024
_SENSITIVE_KEYS = {
    "access_token", "attempt_id", "authorization", "capture_session_id", "image_urls",
    "meal_id", "presigned_url", "subject_id", "task_id", "token", "trace_id", "url", "user_id",
}
_SENSITIVE_KEYS_NORMALIZED = {re.sub(r"[^a-z0-9]", "", key.lower()) for key in _SENSITIVE_KEYS}
_SENSITIVE_KEY_PARTS = ("token", "secret", "authorization", "credential", "password", "cookie", "apikey")
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


@dataclass
class McpToolBindings:
    client: Any
    tools: list[BaseTool]
    called: set[str]
    presented: set[str] = field(default_factory=set)
    capture_payload: dict[str, Any] | None = None

    async def aclose(self) -> None:
        if self.client is not None:
            await self.client.aclose()


class _McpSdkRemoteTool:
    """Small adapter that preserves MCP's reserved per-call `_meta` field."""

    def __init__(self, session: Any, name: str):
        self.session = session
        self.name = name

    async def invoke_with_meta(self, arguments: dict[str, str], tool_call_id: str) -> Any:
        return await self.session.call_tool(
            self.name,
            arguments=arguments,
            meta={"tool_call_id": tool_call_id},
        )


def _normalized_tool_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except (TypeError, ValueError):
        return ""


def _find_tool(tools: Iterable[Any], expected: str, *, stage: str = "list_tools") -> Any:
    normalized = _normalized_tool_name(expected)
    matches = [
        remote
        for remote in tools
        if _normalized_tool_name(remote.name) == normalized
        or _normalized_tool_name(remote.name).endswith(f"_{normalized}")
    ]
    if len(matches) != 1:
        raise McpSetupError(
            f"HealthMind MCP 必须恰好暴露只读工具 {expected}；实际匹配 {len(matches)} 个",
            stage=stage,
        )
    return matches[0]


def _parse_mcp_json(result: Any) -> Any:
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
        raise McpSetupError("HealthMind MCP returned no JSON text", stage="parse_context")
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError as exception:
            raise McpSetupError("HealthMind MCP returned invalid JSON", stage="parse_context") from exception
    raise McpSetupError("HealthMind MCP returned an unsupported response", stage="parse_context")


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
        raise McpSetupError("HealthMind MCP context exceeded the safe response size", stage=stage)
    return serialized, raw_payload


def _stable_tool_call_id(attempt_id: str, full_tool_code: str) -> str:
    """Reuse one MCP audit UUID for retries of this tool in this attempt."""
    try:
        namespace = UUID(attempt_id)
    except ValueError as exception:
        raise ValueError("attempt_id must be a UUID") from exception
    return str(uuid5(namespace, full_tool_code))


async def _invoke_remote(remote: Any, arguments: dict[str, str], tool_call_id: str) -> Any:
    invoke_with_meta = getattr(remote, "invoke_with_meta", None)
    if invoke_with_meta is not None:
        return await invoke_with_meta(arguments, tool_call_id)
    # Compatibility for local/fake LangChain tools. Production uses the MCP
    # SDK directly because langchain-mcp-adapters drops the reserved `_meta`.
    return await remote.ainvoke(
        {
            "type": "tool_call",
            "id": tool_call_id,
            "name": remote.name,
            "args": arguments,
            "_meta": {"tool_call_id": tool_call_id},
        }
    )


def bind_context_tools(
    remote_tools: Iterable[Any],
    *,
    task_id: str,
    attempt_id: str,
    cached_context: dict[str, str] | None = None,
    capture_payload: dict[str, Any] | None = None,
) -> tuple[list[BaseTool], set[str], set[str]]:
    """Expose only the two approved reads, bound to stable per-attempt IDs.

    Production prefetches capture metadata once to obtain its signed image URLs;
    the model-facing capture tool returns that sanitized response. Other tools
    keep their existing model-driven invocation timing. The optional cached
    path is also useful for offline tests.
    """
    called: set[str] = set()
    presented: set[str] = set()
    attempted: set[str] = set()
    capture = _find_tool(remote_tools, CAPTURE_CONTEXT_TOOL)
    nutrition = _find_tool(remote_tools, NUTRITION_CONTEXT_TOOL)
    remotes = {
        "capture_context": (capture, CAPTURE_CONTEXT_TOOL, True),
        "nutrition_context": (nutrition, NUTRITION_CONTEXT_TOOL, False),
    }

    def make_wrapper(name: str, description: str) -> BaseTool:
        remote, full_tool_code, is_capture = remotes[name]

        @tool(name, description=description)
        async def call_bound_context() -> str:
            if name in attempted:
                raise RuntimeError(f"{name} may be called only once for one meal run")
            attempted.add(name)
            started = time.perf_counter()
            try:
                if cached_context is not None and name in cached_context:
                    result = cached_context[name]
                else:
                    raw = await _invoke_remote(
                        remote,
                        {"taskId": task_id, "attemptId": attempt_id},
                        _stable_tool_call_id(attempt_id, full_tool_code),
                    )
                    result, raw_payload = _context_json(raw, capture=is_capture)
                    if is_capture and capture_payload is not None:
                        capture_payload.update(raw_payload)
                    called.add(name)
            except Exception as exception:
                log_event(
                    "mcp.tool.finished",
                    level="ERROR",
                    tool=name,
                    status="error",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    error_type=type(exception).__name__,
                    error_message=str(exception),
                )
                if isinstance(exception, McpSetupError):
                    raise
                raise McpSetupError(
                    f"HealthMind MCP read failed for {name}",
                    stage=f"tool:{name}",
                ) from exception
            log_event(
                "mcp.tool.finished",
                level="INFO",
                tool=name,
                status="success",
                duration_ms=int((time.perf_counter() - started) * 1000),
                result_chars=len(result),
            )
            presented.add(name)
            return result

        return call_bound_context

    tools = [
        make_wrapper(
            "capture_context",
            "Read authorized capture metadata for this task. The tool is already bound to its task and attempt.",
        ),
        make_wrapper(
            "nutrition_context",
            "Read authorized minimal nutrition context for this task. The tool is already bound to its task and attempt.",
        ),
    ]
    return tools, called, presented


async def _access_token(settings: MealSettings) -> str:
    form = {
        "grant_type": "client_credentials",
        "client_id": settings.oauth_client_id,
        "client_secret": settings.oauth_client_secret,
        "scope": settings.mcp_scopes,
    }
    started = time.perf_counter()
    scopes = settings.mcp_scopes or ""
    log_event(
        "mcp.oauth.started",
        level="DEBUG",
        token_host=_host(settings.token_url),
        scope_count=len(scopes.split()),
    )
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as session:
            response = await session.post(settings.token_url, data=form)
    except httpx.HTTPError as exception:
        log_event(
            "mcp.oauth.finished",
            level="DEBUG",
            status="error",
            duration_ms=int((time.perf_counter() - started) * 1000),
            error_type=type(exception).__name__,
        )
        raise McpSetupError("OAuth token endpoint could not be reached", stage="oauth") from exception
    duration_ms = int((time.perf_counter() - started) * 1000)
    if not response.is_success:
        error = McpSetupError(
            f"OAuth token request failed with HTTP {response.status_code}",
            stage="oauth",
        )
        try:
            payload = response.json()
        except (ValueError, AttributeError):
            payload = {}
        if isinstance(payload, dict):
            for key in ("error", "error_description"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    error.add_note(f"oauth_{key}={value[:200]}")
        log_event(
            "mcp.oauth.finished",
            level="DEBUG",
            status="error",
            status_code=response.status_code,
            duration_ms=duration_ms,
            error_type="McpSetupError",
        )
        raise error
    log_event(
        "mcp.oauth.finished",
        level="DEBUG",
        status="success",
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    try:
        access_token = response.json().get("access_token")
    except (ValueError, AttributeError) as exception:
        raise McpSetupError("OAuth token endpoint returned invalid JSON", stage="oauth") from exception
    if not isinstance(access_token, str) or not access_token:
        raise McpSetupError("OAuth token response did not contain access_token", stage="oauth")
    return access_token


async def connect_healthmind_mcp(
    settings: MealSettings,
    *,
    task_id: str,
    attempt_id: str,
) -> McpToolBindings:
    """Open one authenticated streamable HTTP MCP session and prefetch reads."""
    token = await _access_token(settings)
    stage = "connect"
    connected_at = time.perf_counter()
    log_event("mcp.connect.started", level="DEBUG", mcp_host=_host(settings.mcp_url))
    stack = AsyncExitStack()
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        read_stream, write_stream, _ = await stack.enter_async_context(
            streamablehttp_client(
                settings.mcp_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=20,
                sse_read_timeout=20,
            )
        )
        stage = "initialize"
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        stage = "list_tools"
        listed = await session.list_tools()
        tool_names = [item.name for item in listed.tools]
        log_event(
            "mcp.connected",
            level="INFO",
            mcp_host=_host(settings.mcp_url),
            tool_count=len(tool_names),
            tools=tool_names[:20],
            duration_ms=int((time.perf_counter() - connected_at) * 1000),
        )
        remote_tools = [_McpSdkRemoteTool(session, item.name) for item in listed.tools]
        capture = _find_tool(remote_tools, CAPTURE_CONTEXT_TOOL)
        nutrition = _find_tool(remote_tools, NUTRITION_CONTEXT_TOOL)

        stage = "capture_prefetch"
        captured: dict[str, Any] = {}
        prefetch_started = time.perf_counter()
        response = await _invoke_remote(
            capture,
            {"taskId": task_id, "attemptId": attempt_id},
            _stable_tool_call_id(attempt_id, CAPTURE_CONTEXT_TOOL),
        )
        capture_context, raw_payload = _context_json(response, capture=True)
        captured.update(raw_payload)
        images = captured.get("image_urls")
        log_event(
            "mcp.capture.prefetched",
            level="INFO",
            image_count=len(images) if isinstance(images, list) else 0,
            notes_present=bool(captured.get("notes")),
            duration_ms=int((time.perf_counter() - prefetch_started) * 1000),
        )
        safe_context = {"capture_context": capture_context}

        stage = "bind_tools"
        tools, called, presented = bind_context_tools(
            remote_tools,
            task_id=task_id,
            attempt_id=attempt_id,
            cached_context=safe_context,
            capture_payload=captured,
        )
        called.add("capture_context")
        return McpToolBindings(
            client=stack,
            tools=tools,
            called=called,
            presented=presented,
            capture_payload=captured,
        )
    except BaseException as exception:
        try:
            await stack.aclose()
        except BaseException as close_exception:
            log_exception(
                "mcp.close.failed",
                close_exception,
                level="WARNING",
                mcp_stage=stage,
            )
            add_note = getattr(exception, "add_note", None)
            if callable(add_note):
                add_note(f"MCP cleanup failed: {type(close_exception).__name__}")
        if not isinstance(exception, Exception) or isinstance(exception, McpSetupError):
            raise
        raise McpSetupError(
            "Unable to load the required read-only HealthMind MCP tools",
            stage=stage,
        ) from exception
