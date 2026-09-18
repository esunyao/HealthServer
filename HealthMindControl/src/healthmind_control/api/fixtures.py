import asyncio
from fastapi import APIRouter, HTTPException, Query, Request

from ..models import (
    ExecuteRequest, FixtureLifecycleRequest, FixturePreviewRequest,
    McpSessionRequest, OutboxReleaseRequest,
)
from ..security import (
    control_error, redact, replayed_result, require_csrf, require_database_available, sha256_json,
    write_failed_audit, write_started_audit,
)
from ..util import serial


router = APIRouter()


def _require_writes(request: Request, operation_id: str | None = None) -> None:
    if not getattr(request.app.state.db, "connected", True):
        raise control_error(503, "DEPENDENCY_UNAVAILABLE",
                            request.app.state.db.schema_error or "数据库暂不可用，后台正在自动重连",
                            can_retry=True, operation_id=operation_id)
    if not request.app.state.db.write_features.get("fixtures"):
        raise control_error(409, "WRITE_DISABLED",
                            request.app.state.db.schema_error or "数据构造写入已禁用",
                            operation_id=operation_id)


@router.get("/api/fixtures/tables")
async def tables(request: Request):
    require_database_available(request)
    return serial(await request.app.state.repo.fixture_tables())


@router.get("/api/fixtures/sources/{identifier}")
async def source(request: Request, identifier: str, table_name: str | None = Query(None)):
    require_database_available(request)
    try:
        if table_name:
            return serial(redact(await request.app.state.repo.fixture_draft(table_name, identifier)))
        return serial(redact(await request.app.state.repo.fixture_source(identifier)))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/fixtures/draft")
async def draft(request: Request, table_name: str, source_identifier: str | None = None):
    require_database_available(request)
    try:
        return serial(redact(await request.app.state.repo.fixture_draft(table_name, source_identifier)))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/fixtures/preview")
async def fixture_preview(request: Request, body: FixturePreviewRequest):
    require_csrf(request, body.csrf_token)
    _require_writes(request)
    try:
        source_snapshot = await request.app.state.repo.fixture_source_snapshot(body.source_identifier)
        target_snapshot = await request.app.state.repo.fixture_target_snapshot(body.table_name, body.target)
        if body.operation == "update" and not target_snapshot:
            raise RuntimeError("更新目标不存在")
        proposal = await request.app.state.repo.preview_fixture(
            body.operation, body.table_name, body.source_identifier, body.target, body.mappings,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc
    snapshot = {"source": source_snapshot, "target": target_snapshot}
    intent = {
        "operation": body.operation, "table_name": body.table_name,
        "source_identifier": body.source_identifier, "target": body.target,
        "values": proposal["values"], "warnings": proposal["warnings"], "reason": body.reason,
    }
    token, preview = request.app.state.previews.create("fixture.mutate", intent, snapshot)
    return serial({
        "preview_token": token, "expires_at": preview.expires_at * 1000,
        "operation_id": preview.operation_id,
        "confirmation": f"WRITE {body.table_name}", "operation": body.operation,
        "table_name": body.table_name, "values": redact(proposal["values"]),
        "result": redact(proposal["result"]), "warnings": proposal["warnings"],
        "requires_force": bool(proposal["warnings"]), "snapshot": redact(snapshot),
        "sql": f"{body.operation.upper()} {body.table_name} ({', '.join(proposal['values'])})",
    })


@router.post("/api/fixtures/execute")
async def fixture_execute(request: Request, body: ExecuteRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.inspect(body.preview_token, "fixture.mutate")
    intent = preview.payload
    if body.confirmation != f"WRITE {intent['table_name']}":
        raise control_error(409, "CONFIRMATION_MISMATCH", "确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    if intent["warnings"] and not body.accept_warnings:
        raise control_error(409, "WARNINGS_NOT_ACCEPTED", "该操作存在警告，必须在预览中明确接受",
                            can_retry=True, operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(body.preview_token, "fixture.mutate")
    if replayed:
        return serial(replayed_result(cached))
    _require_writes(request, preview.operation_id)
    snapshot = {
        "source": await request.app.state.repo.fixture_source_snapshot(intent["source_identifier"]),
        "target": await request.app.state.repo.fixture_target_snapshot(intent["table_name"], intent["target"]),
    }
    if sha256_json(snapshot) != preview.snapshot_hash:
        raise control_error(409, "PREVIEW_STALE", "源记录或目标记录在预览后发生变化，请重新预览",
                            requires_repreview=True, operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.begin(body.preview_token, "fixture.mutate")
    if replayed:
        return serial(replayed_result(cached))
    op = preview.operation_id
    await write_started_audit(
        request, body.preview_token, "fixture." + intent["operation"], intent["table_name"],
        intent["reason"], op, before=redact(snapshot), proposed=redact(intent["values"]),
    )
    try:
        result = await request.app.state.repo.execute_fixture(
            intent["operation"], intent["table_name"], intent["values"], intent["target"],
        )
        await request.app.state.audit.write(
            "fixture." + intent["operation"], intent["table_name"], intent["reason"], "succeeded",
            operation_id=op, after=redact(result),
        )
        final = serial(redact(result))
        request.app.state.previews.succeed(body.preview_token, final)
        return final
    except Exception as exc:
        await write_failed_audit(request, "fixture." + intent["operation"], intent["table_name"],
                                 intent["reason"], op, exc)
        request.app.state.previews.indeterminate(body.preview_token, str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "写入结果无法确认，请通过操作编号检查审计和目标记录",
                            operation_id=op) from exc


@router.post("/api/fixtures/mcp-session/preview")
async def mcp_session_preview(request: Request, body: McpSessionRequest):
    require_csrf(request, body.csrf_token)
    _require_writes(request)
    source_snapshot = await request.app.state.repo.fixture_source_snapshot(body.source_task_id)
    if not source_snapshot:
        raise HTTPException(404, "源任务不存在")
    try:
        proposal = await request.app.state.repo.prepare_mcp_session(
            body.source_task_id, body.inherit_trace_id,
            request.app.state.settings.fixture_mcp_lease_minutes,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    frozen = {key: proposal[key] for key in (
        "task_id", "attempt_id", "trace_id", "session_id", "lease_until", "source_task_id", "manifest",
    )}
    frozen["reason"] = body.reason
    token, preview = request.app.state.previews.create("fixture.mcp.create", frozen, source_snapshot)
    return serial({
        "preview_token": token, "expires_at": preview.expires_at * 1000,
        "operation_id": preview.operation_id,
        "confirmation": f"MCP TEST {body.source_task_id}",
        "source_task_id": body.source_task_id,
        "dify_inputs": {key: proposal[key] for key in ("task_id", "attempt_id", "trace_id")},
        "lease_until": proposal["lease_until"], "tools": proposal["bindings"],
        "database_writes": ["healthmind.ai_tasks", "healthmind.ai_task_attempts"],
        "kafka_writes": 0, "nutri_writes": 0, "snapshot": redact(source_snapshot),
    })


@router.post("/api/fixtures/mcp-session/execute")
async def mcp_session_execute(request: Request, body: ExecuteRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.inspect(body.preview_token, "fixture.mcp.create")
    intent = preview.payload
    if body.confirmation != f"MCP TEST {intent['source_task_id']}":
        raise control_error(409, "CONFIRMATION_MISMATCH", "确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(body.preview_token, "fixture.mcp.create")
    if replayed:
        return serial(replayed_result(cached))
    _require_writes(request, preview.operation_id)
    current = await request.app.state.repo.fixture_source_snapshot(intent["source_task_id"])
    if not current or sha256_json(current) != preview.snapshot_hash:
        raise control_error(409, "PREVIEW_STALE", "源任务在预览后发生变化，请重新预览",
                            requires_repreview=True, operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.begin(body.preview_token, "fixture.mcp.create")
    if replayed:
        return serial(replayed_result(cached))
    op = preview.operation_id
    await write_started_audit(
        request, body.preview_token, "fixture.mcp.create", intent["source_task_id"], intent["reason"], op,
        generated={key: intent[key] for key in ("task_id", "attempt_id", "trace_id")},
    )
    try:
        result = await request.app.state.repo.create_mcp_session(intent)
        run = await asyncio.to_thread(
            request.app.state.debug_store.create,
            f"MCP test {result['task_id'][:8]}", "emulated",
            {**result, "source_task_id": intent["source_task_id"]},
        )
        await asyncio.to_thread(
            request.app.state.debug_store.record, run["run_id"], "mcp_fixture",
            "fixture.mcp.create", "succeeded", result,
        )
        result["debug_run_id"] = run["run_id"]
        await request.app.state.audit.write(
            "fixture.mcp.create", intent["source_task_id"], intent["reason"], "succeeded",
            operation_id=op, result=result,
        )
        final = serial(result)
        request.app.state.previews.succeed(body.preview_token, final)
        return final
    except Exception as exc:
        await write_failed_audit(request, "fixture.mcp.create", intent["source_task_id"], intent["reason"], op, exc)
        request.app.state.previews.indeterminate(body.preview_token, str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "MCP 测试记录写入结果无法确认，请通过操作编号检查审计",
                            operation_id=op) from exc


async def _lifecycle_preview(request: Request, task_id: str, reason: str, action: str):
    session = await request.app.state.repo.mcp_session(task_id)
    if not session:
        raise HTTPException(404, "MCP 调试任务不存在")
    token, preview = request.app.state.previews.create(
        f"fixture.mcp.{action}", {"task_id": task_id, "reason": reason}, session,
    )
    return serial({
        "preview_token": token, "expires_at": preview.expires_at * 1000,
        "operation_id": preview.operation_id,
        "confirmation": f"{action.upper()} {task_id}", "snapshot": redact(session),
    })


async def _lifecycle_execute(request: Request, task_id: str, body: ExecuteRequest, action: str):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.inspect(body.preview_token, f"fixture.mcp.{action}")
    if preview.payload["task_id"] != task_id or body.confirmation != f"{action.upper()} {task_id}":
        raise control_error(409, "CONFIRMATION_MISMATCH", "预览目标或确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(
        body.preview_token, f"fixture.mcp.{action}",
    )
    if replayed:
        return serial(replayed_result(cached))
    _require_writes(request, preview.operation_id)
    current = await request.app.state.repo.mcp_session(task_id)
    if not current or sha256_json(current) != preview.snapshot_hash:
        raise control_error(409, "PREVIEW_STALE", "调试任务在预览后发生变化，请重新预览",
                            requires_repreview=True, operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.begin(
        body.preview_token, f"fixture.mcp.{action}",
    )
    if replayed:
        return serial(replayed_result(cached))
    reason = preview.payload["reason"]
    op = preview.operation_id
    await write_started_audit(request, body.preview_token, f"fixture.mcp.{action}", task_id, reason, op)
    try:
        result = (await request.app.state.repo.renew_mcp_session(
            task_id, request.app.state.settings.fixture_mcp_lease_minutes,
        )) if action == "renew" else await request.app.state.repo.close_mcp_session(task_id)
        await request.app.state.audit.write(
            f"fixture.mcp.{action}", task_id, reason, "succeeded", operation_id=op, result=result,
        )
        final = serial(result)
        request.app.state.previews.succeed(body.preview_token, final)
        return final
    except RuntimeError as exc:
        request.app.state.previews.release(body.preview_token, str(exc))
        await write_failed_audit(request, f"fixture.mcp.{action}", task_id, reason, op, exc)
        raise control_error(409, "EXECUTION_REJECTED", str(exc), can_retry=True,
                            operation_id=op) from exc
    except Exception as exc:
        await write_failed_audit(request, f"fixture.mcp.{action}", task_id, reason, op, exc)
        request.app.state.previews.indeterminate(body.preview_token, str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "会话操作结果无法确认，请通过操作编号检查审计和目标记录",
                            operation_id=op) from exc


@router.post("/api/fixtures/mcp-session/{task_id}/renew/preview")
async def renew_preview(request: Request, task_id: str, body: FixtureLifecycleRequest):
    require_csrf(request, body.csrf_token)
    if body.task_id != task_id:
        raise HTTPException(409, "请求体 task_id 与路径不一致")
    return await _lifecycle_preview(request, task_id, body.reason, "renew")


@router.post("/api/fixtures/mcp-session/{task_id}/renew")
async def renew_execute(request: Request, task_id: str, body: ExecuteRequest):
    return await _lifecycle_execute(request, task_id, body, "renew")


@router.post("/api/fixtures/mcp-session/{task_id}/close/preview")
async def close_preview(request: Request, task_id: str, body: FixtureLifecycleRequest):
    require_csrf(request, body.csrf_token)
    if body.task_id != task_id:
        raise HTTPException(409, "请求体 task_id 与路径不一致")
    return await _lifecycle_preview(request, task_id, body.reason, "close")


@router.post("/api/fixtures/mcp-session/{task_id}/close")
async def close_execute(request: Request, task_id: str, body: ExecuteRequest):
    return await _lifecycle_execute(request, task_id, body, "close")


@router.get("/api/fixtures/mcp-session/{task_id}/invocations")
async def session_invocations(request: Request, task_id: str):
    session = await request.app.state.repo.mcp_session(task_id)
    if not session:
        raise HTTPException(404, "MCP 调试任务不存在")
    return serial({"session": redact(session), "invocations": redact(
        await request.app.state.repo.mcp_session_invocations(task_id),
    )})


@router.post("/api/fixtures/outbox/release/preview")
async def outbox_release_preview(request: Request, body: OutboxReleaseRequest):
    require_csrf(request, body.csrf_token)
    table = f"{body.schema_name}.integration_outbox"
    snapshot = await request.app.state.repo.fixture_target_snapshot(table, {"event_id": body.event_id})
    if not snapshot:
        raise HTTPException(404, "outbox 不存在")
    intent = {"schema_name": body.schema_name, "event_id": body.event_id, "reason": body.reason}
    token, preview = request.app.state.previews.create("fixture.outbox.release", intent, snapshot)
    return serial({"preview_token": token, "expires_at": preview.expires_at * 1000,
                   "operation_id": preview.operation_id,
                   "confirmation": f"RELEASE {body.event_id}", "snapshot": redact(snapshot)})


@router.post("/api/fixtures/outbox/release")
async def outbox_release_execute(request: Request, body: ExecuteRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.inspect(body.preview_token, "fixture.outbox.release")
    intent = preview.payload
    if body.confirmation != f"RELEASE {intent['event_id']}":
        raise control_error(409, "CONFIRMATION_MISMATCH", "确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(body.preview_token, "fixture.outbox.release")
    if replayed:
        return serial(replayed_result(cached))
    _require_writes(request, preview.operation_id)
    table = f"{intent['schema_name']}.integration_outbox"
    current = await request.app.state.repo.fixture_target_snapshot(table, {"event_id": intent["event_id"]})
    if not current or sha256_json(current) != preview.snapshot_hash:
        raise control_error(409, "PREVIEW_STALE", "outbox 在预览后发生变化，请重新预览",
                            requires_repreview=True, operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.begin(body.preview_token, "fixture.outbox.release")
    if replayed:
        return serial(replayed_result(cached))
    op = preview.operation_id
    await write_started_audit(request, body.preview_token, "fixture.outbox.release", intent["event_id"],
                              intent["reason"], op)
    try:
        result = await request.app.state.repo.release_fixture_outbox(intent["schema_name"], intent["event_id"])
        await request.app.state.audit.write("fixture.outbox.release", intent["event_id"], intent["reason"],
                                            "succeeded", operation_id=op, result=result)
        final = serial(redact(result))
        request.app.state.previews.succeed(body.preview_token, final)
        return final
    except Exception as exc:
        await write_failed_audit(request, "fixture.outbox.release", intent["event_id"], intent["reason"], op, exc)
        request.app.state.previews.indeterminate(body.preview_token, str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "outbox 放行结果无法确认，请通过操作编号检查审计和目标记录",
                            operation_id=op) from exc
