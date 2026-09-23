"""Read-only HealthMind MCP tools with task and attempt IDs bound by the CLI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable
from uuid import uuid4

import httpx
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, tool

from .config import MealSettings

CAPTURE_CONTEXT_TOOL = "nutrimemo.capture_context.get"
NUTRITION_CONTEXT_TOOL = "orion.nutrition_context.get"
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
_SENSITIVE_KEY_PARTS = ("token", "secret", "authorization", "credential", "password", "cookie", "apikey")
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


class McpSetupError(RuntimeError):
    """The configured HealthMind MCP or OAuth client could not be initialized."""


@dataclass
class McpToolBindings:
    client: Any
    tools: list[BaseTool]
    called: set[str]


def _normalized_tool_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _find_tool(tools: Iterable[BaseTool], expected: str) -> BaseTool:
    normalized = _normalized_tool_name(expected)
    matches = [
        remote
        for remote in tools
        if _normalized_tool_name(remote.name) == normalized
        or _normalized_tool_name(remote.name).endswith(f"_{normalized}")
    ]
    if len(matches) != 1:
        raise McpSetupError(f"HealthMind MCP 必须恰好暴露只读工具 {expected}；实际匹配 {len(matches)} 个")
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
    if isinstance(result, dict):
        if "structuredContent" in result:
            return result["structuredContent"]
        if "content" in result:
            return _parse_mcp_json(result["content"])
        return result
    if isinstance(result, list):
        texts = [item.get("text") for item in result if isinstance(item, dict) and item.get("type") == "text"]
        if len(texts) == 1 and isinstance(texts[0], str):
            return _parse_mcp_json(texts[0])
        if texts:
            return _parse_mcp_json("\n".join(texts))
        raise McpSetupError("HealthMind MCP returned no JSON text")
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError as exception:
            raise McpSetupError("HealthMind MCP returned invalid JSON") from exception
    raise McpSetupError("HealthMind MCP returned an unsupported response")


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


def _context_json(result: Any, *, capture: bool) -> str:
    payload = _parse_mcp_json(result)
    if not isinstance(payload, dict):
        raise McpSetupError("HealthMind MCP context must be a JSON object")
    images = payload.get("image_urls")
    image_count = len(images) if isinstance(images, list) else 0
    payload = _remove_sensitive_fields(payload)
    if capture:
        payload["confirmed_image_count"] = image_count
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > MAX_CONTEXT_CHARS:
        raise McpSetupError("HealthMind MCP context exceeded the safe response size")
    return serialized


def bind_context_tools(
    remote_tools: Iterable[BaseTool],
    *,
    task_id: str,
    attempt_id: str,
) -> tuple[list[BaseTool], set[str]]:
    """Expose only the two approved reads; hide identifiers from model arguments."""
    called: set[str] = set()
    attempted: set[str] = set()
    capture = _find_tool(remote_tools, CAPTURE_CONTEXT_TOOL)
    nutrition = _find_tool(remote_tools, NUTRITION_CONTEXT_TOOL)

    def make_wrapper(remote: BaseTool, name: str, description: str, *, is_capture: bool) -> BaseTool:
        @tool(name, description=description)
        async def call_bound_context() -> str:
            if name in attempted:
                raise RuntimeError(f"{name} may be called only once for one meal run")
            attempted.add(name)
            try:
                raw = await remote.ainvoke(
                    {
                        "type": "tool_call",
                        "id": str(uuid4()),
                        "name": remote.name,
                        "args": {"taskId": task_id, "attemptId": attempt_id},
                    }
                )
            except Exception as exception:
                raise McpSetupError(f"HealthMind MCP read failed for {name}") from exception
            result = _context_json(raw, capture=is_capture)
            called.add(name)
            return result

        return call_bound_context

    tools = [
        make_wrapper(
            capture,
            "capture_context",
            "Read authorized capture metadata for this task. The tool is already bound to its task and attempt.",
            is_capture=True,
        ),
        make_wrapper(
            nutrition,
            "nutrition_context",
            "Read authorized minimal nutrition context for this task. The tool is already bound to its task and attempt.",
            is_capture=False,
        ),
    ]
    return tools, called


async def _access_token(settings: MealSettings) -> str:
    form = {
        "grant_type": "client_credentials",
        "client_id": settings.oauth_client_id,
        "client_secret": settings.oauth_client_secret,
        "scope": settings.mcp_scopes,
    }
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as session:
            response = await session.post(settings.token_url, data=form)
    except httpx.HTTPError as exception:
        raise McpSetupError("OAuth token endpoint could not be reached") from exception
    if not response.is_success:
        raise McpSetupError(f"OAuth token request failed with HTTP {response.status_code}")
    try:
        access_token = response.json().get("access_token")
    except (ValueError, AttributeError) as exception:
        raise McpSetupError("OAuth token endpoint returned invalid JSON") from exception
    if not isinstance(access_token, str) or not access_token:
        raise McpSetupError("OAuth token response did not contain access_token")
    return access_token


async def connect_healthmind_mcp(
    settings: MealSettings,
    *,
    task_id: str,
    attempt_id: str,
) -> McpToolBindings:
    # Keep the optional adapter import lazy so offline contract/tool tests can
    # run before this project's environment has been synchronized.
    from langchain_mcp_adapters.client import MultiServerMCPClient

    token = await _access_token(settings)
    client = MultiServerMCPClient(
        {
            "healthmind": {
                "transport": "streamable_http",
                "url": settings.mcp_url,
                "headers": {"Authorization": f"Bearer {token}"},
                "timeout": 20,
                "sse_read_timeout": 20,
            }
        },
        handle_tool_errors=False,
    )
    try:
        remote_tools = await client.get_tools()
        tools, called = bind_context_tools(remote_tools, task_id=task_id, attempt_id=attempt_id)
    except Exception as exception:
        if isinstance(exception, McpSetupError):
            raise
        raise McpSetupError("Unable to load the required read-only HealthMind MCP tools") from exception
    return McpToolBindings(client=client, tools=tools, called=called)
