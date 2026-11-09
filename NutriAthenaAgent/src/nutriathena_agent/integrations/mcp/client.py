"""OAuth and streamable HTTP SDK lifecycle for HealthMind context reads."""

from __future__ import annotations

import time
from contextlib import AsyncExitStack
from typing import Any
from urllib.parse import urlsplit

import httpx

from ...config import MealSettings
from ...observability import log_event, log_exception
from .context import McpSetupError, _context_json
from .tools import (
    CAPTURE_CONTEXT_TOOL,
    NUTRITION_CONTEXT_TOOL,
    McpToolBindings,
    _McpSdkRemoteTool,
    _find_tool,
    _invoke_remote,
    _stable_tool_call_id,
    bind_context_tools,
)

def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except (TypeError, ValueError):
        return ""


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
        _find_tool(remote_tools, NUTRITION_CONTEXT_TOOL)

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
