"""Run one authorized meal attempt through the LangChain agent."""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from ..config import build_meal_model, load_meal_settings
from ..debug import DebugTraceCallback, DebugTracer
from ..execution.ports import MealRunner
from ..images import ImageInputError, image_message_parts, load_captured_images
from ..logging_service import (
    configure_logging,
    log_context,
    log_event,
    log_exception,
    render_exception,
)
from ..mcp_tools import CaptureContext, McpSetupError, connect_healthmind_mcp
from .agent import REQUIRED_CONTEXT_TOOLS, build_meal_agent
from .contract import NeedsReview, parse_meal_result, result_dict
from .input import _final_text, _load_evidence, _meal_request
from .prompt import build_system_prompt


class LangChainMealRunner:
    """Production runner around the LangChain tool loop and maintained prompt."""

    async def run(self, *, task_id: str, attempt_id: str, trace_id: str = "") -> dict[str, object]:
        started = time.perf_counter()
        stage = "init"
        status = "error"
        reason_code: str | None = None
        error_type: str | None = None
        settings = None
        tracer: DebugTracer | None = None
        mcp = None
        with log_context(
            trace_id=trace_id or None,
            task_id=str(task_id),
            attempt_id=str(attempt_id),
        ):
            try:
                task_id = str(UUID(task_id))
                attempt_id = str(UUID(attempt_id))
                stage = "settings"
                settings = load_meal_settings()
                configure_logging(settings.debug_level)
                tracer = DebugTracer(settings.debug_level, trace_id=trace_id or "-")
                log_event(
                    "meal.started",
                    level="INFO",
                    model=settings.model,
                    debug_level=settings.debug_level,
                )

                stage = "mcp"
                mcp = await connect_healthmind_mcp(settings, task_id=task_id, attempt_id=attempt_id)
                raw_images = mcp.capture_payload.get("image_urls", []) if mcp.capture_payload else []
                candidate_count = len(raw_images) if isinstance(raw_images, list) else 0

                stage = "images"
                images_started = time.perf_counter()
                try:
                    images = await load_captured_images(
                        raw_images,
                        allowed_hosts=settings.media_allowed_hosts,
                        max_images=settings.max_images,
                        max_image_bytes=settings.max_image_bytes,
                        max_total_bytes=settings.max_total_image_bytes,
                    )
                except ImageInputError as exception:
                    status, reason_code = "needs_review", "IMAGE_UNAVAILABLE"
                    error_type = type(exception).__name__
                    log_event(
                        "meal.images.unavailable",
                        level="WARNING",
                        reason_code="IMAGE_UNAVAILABLE",
                        error_type=error_type,
                        error_message=str(exception),
                        candidate_count=candidate_count,
                        duration_ms=int((time.perf_counter() - images_started) * 1000),
                    )
                    return result_dict(
                        NeedsReview(
                            status="needs_review",
                            reason_code="IMAGE_UNAVAILABLE",
                            message="授权餐食图片当前不可用或不符合安全要求，请确认图片后重试。",
                        )
                    )
                if not images:
                    status, reason_code = "needs_review", "IMAGE_UNAVAILABLE"
                    log_event(
                        "meal.images.unavailable",
                        level="WARNING",
                        reason_code="IMAGE_UNAVAILABLE",
                        reason="no_images",
                        candidate_count=candidate_count,
                        duration_ms=int((time.perf_counter() - images_started) * 1000),
                    )
                    return result_dict(
                        NeedsReview(
                            status="needs_review",
                            reason_code="IMAGE_UNAVAILABLE",
                            message="本次餐食没有可用的授权图片，无法可靠识别。",
                        )
                    )
                log_event(
                    "meal.images.loaded",
                    level="INFO",
                    count=len(images),
                    total_bytes=sum(len(image.data) for image in images),
                    mime_types=[image.mime_type for image in images],
                    duration_ms=int((time.perf_counter() - images_started) * 1000),
                )

                stage = "context"
                capture_context = CaptureContext.model_validate(mcp.capture_payload or {})
                log_event(
                    "meal.context",
                    level="INFO",
                    images=len(images),
                    notes_present=bool(capture_context.notes),
                )

                stage = "prompt"
                evidence = _load_evidence(None, settings)
                system_prompt = build_system_prompt()

                stage = "model"
                model = build_meal_model(settings)

                stage = "agent_build"
                agent = build_meal_agent(model, mcp.tools, system_prompt)
                message_parts: list[dict[str, object]] = [
                    {"type": "text", "text": _meal_request(capture_context.notes, evidence, images)},
                    *image_message_parts(images),
                ]
                config: dict[str, Any] = {"recursion_limit": 12}
                if tracer.enabled:
                    config["callbacks"] = [DebugTraceCallback(tracer)]

                stage = "agent_invoke"
                log_event(
                    "meal.agent.started",
                    level="INFO",
                    tools=len(mcp.tools),
                    message_parts=len(message_parts),
                    recursion_limit=12,
                )
                invoke_started = time.perf_counter()
                response = await agent.ainvoke(
                    {"messages": [HumanMessage(content=message_parts)]},
                    config=config,
                )
                messages = response.get("messages")
                try:
                    output_chars = len(_final_text(response))
                except Exception:
                    output_chars = 0
                log_event(
                    "meal.agent.finished",
                    level="INFO",
                    duration_ms=int((time.perf_counter() - invoke_started) * 1000),
                    messages=len(messages) if isinstance(messages, list) else 0,
                    output_chars=output_chars,
                )

                stage = "contract"
                missing_tools = sorted(REQUIRED_CONTEXT_TOOLS - mcp.presented)
                if missing_tools:
                    log_event(
                        "meal.tools.missing",
                        level="ERROR",
                        missing=missing_tools,
                    )
                    raise McpSetupError(
                        f"Agent 未读取所需的 HealthMind 上下文工具：{', '.join(missing_tools)}",
                        stage="tools",
                    )
                final_text = _final_text(response)
                if tracer.full:
                    tracer.content("meal.model_output", final_text)
                try:
                    parsed = parse_meal_result(final_text)
                except (ValidationError, ValueError, json.JSONDecodeError) as exception:
                    error_type = type(exception).__name__
                    status, reason_code = "needs_review", "CONTRACT_INVALID"
                    validation_errors = (
                        render_exception(exception, content=False)[1]
                        if isinstance(exception, ValidationError)
                        else None
                    )
                    log_event(
                        "meal.contract.invalid",
                        level="WARNING",
                        error_type=error_type,
                        error_message=str(exception),
                        output_chars=len(final_text),
                        validation_errors=validation_errors,
                    )
                    parsed = NeedsReview(
                        status="needs_review",
                        reason_code="CONTRACT_INVALID",
                        message="模型结果不是符合 HealthMind 契约的严格 JSON，未生成可入库结果。",
                    )
                if isinstance(parsed, NeedsReview):
                    status, reason_code = "needs_review", parsed.reason_code
                else:
                    status = "analysis"
                result = result_dict(parsed)
                if tracer.full:
                    tracer.content(
                        "meal.result",
                        json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    )
                stage = "done"
                return result
            except Exception as exception:
                error_type = type(exception).__name__
                mcp_stage = getattr(exception, "stage", None)
                log_exception(
                    "meal.failed",
                    exception,
                    stage=mcp_stage or stage,
                    mcp_stage=mcp_stage,
                    status=status,
                    reason_code=reason_code,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
                raise
            finally:
                if mcp is not None:
                    try:
                        await mcp.aclose()
                    except Exception as exception:
                        log_exception(
                            "meal.mcp.close_failed",
                            exception,
                            level="WARNING",
                            stage="close",
                        )
                log_event(
                    "meal.finished",
                    level="INFO",
                    stage=stage,
                    status=status,
                    reason_code=reason_code,
                    error_type=error_type,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )


_DEFAULT_RUNNER = LangChainMealRunner()


async def run_meal_analysis(
    *,
    task_id: str,
    attempt_id: str,
    trace_id: str = "",
    runner: MealRunner | None = None,
) -> dict[str, object]:
    """Run one attempt through a swappable runner and return the shared result contract."""
    return await (runner or _DEFAULT_RUNNER).run(
        task_id=task_id,
        attempt_id=attempt_id,
        trace_id=trace_id,
    )
