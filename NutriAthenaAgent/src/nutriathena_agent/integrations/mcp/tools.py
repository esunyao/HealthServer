"""Per-attempt read-only MCP tools and SDK metadata transport."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable
from uuid import UUID, uuid5

from langchain_core.tools import BaseTool, tool

from ...observability import log_event, log_exception
from .context import McpSetupError, _context_json

CAPTURE_CONTEXT_TOOL = "nutrimemo.capture_context.get"


NUTRITION_CONTEXT_TOOL = "orion.nutrition_context.get"


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

    async def invoke_with_meta(
        self, arguments: dict[str, str], tool_call_id: str
    ) -> Any:
        return await self.session.call_tool(
            self.name,
            arguments=arguments,
            meta={"tool_call_id": tool_call_id},
        )


def _normalized_tool_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _find_tool(
    tools: Iterable[Any], expected: str, *, stage: str = "list_tools"
) -> Any:
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


def _stable_tool_call_id(attempt_id: str, full_tool_code: str) -> str:
    """Reuse one MCP audit UUID for retries of this tool in this attempt."""
    try:
        namespace = UUID(attempt_id)
    except ValueError as exception:
        raise ValueError("attempt_id must be a UUID") from exception
    return str(uuid5(namespace, full_tool_code))


async def _invoke_remote(
    remote: Any, arguments: dict[str, str], tool_call_id: str
) -> Any:
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
    remote_tools = list(remote_tools)
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
                log_exception(
                    "mcp.tool.finished",
                    exception,
                    level="ERROR",
                    tool=name,
                    status="error",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    mcp_stage=getattr(exception, "stage", f"tool:{name}"),
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
