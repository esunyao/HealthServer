"""LangChain execution callbacks: node, model and tool lifecycle events."""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from .tracer import DebugTracer

_IMAGE_BLOCK_TYPES = frozenset({"image_url", "input_image", "image"})


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif block_type in _IMAGE_BLOCK_TYPES:
                    parts.append(f"[image omitted: {_image_mime(block)}]")
                else:
                    parts.append(f"[{block_type or 'block'}]")
            else:
                parts.append(f"[{type(block).__name__}]")
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def _image_mime(block: dict[str, Any]) -> str:
    image = block.get("image_url") or block.get("image") or block.get("source")
    url = image.get("url") if isinstance(image, dict) else image
    if isinstance(url, str) and url.startswith("data:"):
        mime = url[5:].split(";", 1)[0]
        return mime or "image"
    return "image"


def _message_text(message: Any) -> str:
    return _content_text(getattr(message, "content", message))


def _tool_output_text(output: Any) -> str:
    content = getattr(output, "content", None)
    return _content_text(content if content is not None else output)


def _model_name(
    serialized: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    kwargs: dict[str, Any],
) -> str:
    serialized = serialized or {}
    serialized_kwargs = serialized.get("kwargs") or {}
    invocation = kwargs.get("invocation_params") or {}
    for candidate in (
        serialized_kwargs.get("model_name"),
        serialized_kwargs.get("model"),
        invocation.get("model"),
        (metadata or {}).get("ls_model_name"),
    ):
        if isinstance(candidate, str) and candidate:
            return candidate
    name = serialized.get("name")
    return name if isinstance(name, str) and name else "unknown"


def _tool_name(serialized: dict[str, Any] | None, kwargs: dict[str, Any]) -> str:
    serialized = serialized or {}
    for candidate in (serialized.get("name"), kwargs.get("name")):
        if isinstance(candidate, str) and candidate:
            return candidate
    return "tool"


def _first_message(response: LLMResult) -> Any:
    generations = getattr(response, "generations", None)
    if not generations or not generations[0]:
        return None
    return getattr(generations[0][0], "message", None)


def _token_usage(response: LLMResult, message: Any) -> dict[str, int | None]:
    usage: dict[str, Any] = {}
    llm_output = getattr(response, "llm_output", None)
    if isinstance(llm_output, dict):
        raw = llm_output.get("token_usage") or llm_output.get("usage")
        if isinstance(raw, dict):
            usage = raw
    if not usage and message is not None:
        raw = getattr(message, "usage_metadata", None)
        if isinstance(raw, dict):
            usage = raw
    prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion = usage.get("completion_tokens", usage.get("output_tokens"))
    total = usage.get("total_tokens")
    if total is None and isinstance(prompt, int) and isinstance(completion, int):
        total = prompt + completion
    return {
        "prompt_tokens": prompt if isinstance(prompt, int) else None,
        "completion_tokens": completion if isinstance(completion, int) else None,
        "total_tokens": total if isinstance(total, int) else None,
    }


def _finish_reason(response: LLMResult) -> str | None:
    generations = getattr(response, "generations", None)
    if not generations or not generations[0]:
        return None
    generation = generations[0][0]
    info = getattr(generation, "generation_info", None)
    if isinstance(info, dict) and isinstance(info.get("finish_reason"), str):
        return info["finish_reason"]
    message = getattr(generation, "message", None)
    metadata = getattr(message, "response_metadata", None)
    if isinstance(metadata, dict) and isinstance(metadata.get("finish_reason"), str):
        return metadata["finish_reason"]
    return None


class DebugTraceCallback(AsyncCallbackHandler):
    """Emit step events without ever failing the agent run."""

    raise_error = False

    def __init__(self, tracer: DebugTracer) -> None:
        super().__init__()
        self.tracer = tracer
        self._started: dict[UUID, float] = {}
        self._node_runs: dict[UUID, str] = {}
        self._tool_names: dict[UUID, str] = {}

    def _duration_ms(self, run_id: UUID) -> int | None:
        started = self._started.pop(run_id, None)
        if started is None:
            return None
        return int((time.perf_counter() - started) * 1000)

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del inputs, parent_run_id, tags
        node = (metadata or {}).get("langgraph_node")
        if isinstance(node, str) and node and kwargs.get("name") == node:
            self._node_runs[run_id] = node
            self._started[run_id] = time.perf_counter()
            self.tracer.event("node.started", node=node)

    async def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        del outputs, parent_run_id, tags, kwargs
        node = self._node_runs.pop(run_id, None)
        if node is not None:
            self.tracer.event(
                "node.finished", node=node, duration_ms=self._duration_ms(run_id)
            )

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, tags, kwargs
        node = self._node_runs.pop(run_id, None)
        if node is not None:
            self.tracer.event(
                "node.error",
                node=node,
                duration_ms=self._duration_ms(run_id),
                error_type=type(error).__name__,
            )
            if self.tracer.full:
                self.tracer.content("node.error.message", str(error))

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, tags
        self._started[run_id] = time.perf_counter()
        flat = messages[0] if messages else []
        roles: dict[str, int] = {}
        image_parts = 0
        for message in flat:
            role = getattr(message, "type", type(message).__name__)
            roles[role] = roles.get(role, 0) + 1
            content = getattr(message, "content", None)
            if isinstance(content, list):
                image_parts += sum(
                    1
                    for block in content
                    if isinstance(block, dict)
                    and block.get("type") in _IMAGE_BLOCK_TYPES
                )
        self.tracer.event(
            "llm.started",
            model=_model_name(serialized, metadata, kwargs),
            messages=len(flat),
            roles=roles,
            image_parts=image_parts,
        )
        if self.tracer.full:
            for index, message in enumerate(flat):
                self.tracer.content(f"llm.input[{index}]", _message_text(message))

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, tags, kwargs
        duration = self._duration_ms(run_id)
        message = _first_message(response)
        text = _message_text(message) if message is not None else ""
        raw_calls = (
            getattr(message, "tool_calls", None) if message is not None else None
        )
        tool_calls = [
            call.get("name")
            for call in raw_calls or []
            if isinstance(call, dict) and isinstance(call.get("name"), str)
        ]
        usage = _token_usage(response, message)
        self.tracer.event(
            "llm.finished",
            duration_ms=duration,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            finish_reason=_finish_reason(response),
            tool_calls=tool_calls,
            output_chars=len(text),
        )
        if self.tracer.full:
            self.tracer.content("llm.output", text)
            if raw_calls:
                self.tracer.content(
                    "llm.tool_calls",
                    json.dumps(raw_calls, ensure_ascii=False, default=str),
                )

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, tags, kwargs
        self.tracer.event(
            "llm.error",
            duration_ms=self._duration_ms(run_id),
            error_type=type(error).__name__,
        )
        if self.tracer.full:
            self.tracer.content("llm.error.message", str(error))

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, tags, metadata, inputs
        name = _tool_name(serialized, kwargs)
        self._tool_names[run_id] = name
        self._started[run_id] = time.perf_counter()
        self.tracer.event("tool.started", tool=name)
        if self.tracer.full:
            self.tracer.content("tool.input", input_str)

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, tags
        name = self._tool_names.pop(run_id, kwargs.get("name", "tool"))
        text = _tool_output_text(output)
        self.tracer.event(
            "tool.finished",
            tool=name,
            duration_ms=self._duration_ms(run_id),
            output_chars=len(text),
        )
        if self.tracer.full:
            self.tracer.content("tool.output", text)

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, tags, kwargs
        name = self._tool_names.pop(run_id, "tool")
        self.tracer.event(
            "tool.error",
            tool=name,
            duration_ms=self._duration_ms(run_id),
            error_type=type(error).__name__,
        )
        if self.tracer.full:
            self.tracer.content("tool.error.message", str(error))
