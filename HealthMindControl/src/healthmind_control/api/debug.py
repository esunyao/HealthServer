import asyncio

from fastapi import APIRouter, HTTPException, Query, Request

from ..models import DebugRunRequest, DebugStepRequest, ExecuteRequest
from ..security import (
    control_error, redact, replayed_result, require_csrf, sha256_json,
    write_failed_audit, write_started_audit,
)
from ..util import serial

router = APIRouter()


@router.get("/api/debug/runs")
async def runs(request: Request, limit: int = Query(100, ge=1, le=100)):
    return serial(await asyncio.to_thread(request.app.state.debug_store.list, limit))


@router.post("/api/debug/runs")
async def create_run(request: Request, body: DebugRunRequest):
    require_csrf(request, body.csrf_token)
    context = {str(k): str(v) if isinstance(v, int) else v for k, v in body.context.items()}
    return serial(await asyncio.to_thread(request.app.state.debug_store.create, body.name, body.mode, context))


@router.get("/api/debug/runs/{run_id}")
async def run_detail(request: Request, run_id: str):
    run = await asyncio.to_thread(request.app.state.debug_store.get, run_id)
    if not run:
        raise HTTPException(404, "debug run not found")
    return serial(redact(run))


@router.get("/api/debug/runs/{run_id}/observe")
async def observe(request: Request, run_id: str):
    run = await asyncio.to_thread(request.app.state.debug_store.get, run_id)
    if not run:
        raise HTTPException(404, "debug run not found")
    return serial(redact(await request.app.state.debug.observe(run)))


@router.get("/api/debug/users")
async def users(request: Request, q: str = Query(min_length=2, max_length=200)):
    return serial(await request.app.state.debug.users(q))


@router.post("/api/debug/runs/{run_id}/steps/{step}/preview")
async def step_preview(request: Request, run_id: str, step: str, body: DebugStepRequest):
    require_csrf(request, body.csrf_token)
    run = await asyncio.to_thread(request.app.state.debug_store.get, run_id)
    if not run:
        raise HTTPException(404, "debug run not found")
    try:
        proposal = await request.app.state.debug.preview_step(run, step, body.params | {"record_id": body.record_id})
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    intent = {"run_id": run_id, "step": step, "record_id": proposal["record_id"],
              "params": body.params, "reason": body.reason}
    token, preview = request.app.state.previews.create(f"debug.{step}", intent, proposal["snapshot"])
    return serial({"preview_token": token, "expires_at": preview.expires_at,
                   "operation_id": preview.operation_id,
                   "snapshot": redact(proposal["snapshot"]), "confirmation": f"STEP {step.upper()}"})


@router.post("/api/debug/runs/{run_id}/steps/{step}/execute")
async def step_execute(request: Request, run_id: str, step: str, body: ExecuteRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.inspect(body.preview_token, f"debug.{step}")
    intent = preview.payload
    if intent["run_id"] != run_id or intent["step"] != step:
        raise control_error(409, "PREVIEW_TARGET_MISMATCH", "预览目标不匹配",
                            requires_repreview=True, operation_id=preview.operation_id)
    if body.confirmation != f"STEP {step.upper()}":
        raise control_error(409, "CONFIRMATION_MISMATCH", "确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(body.preview_token, f"debug.{step}")
    if replayed:
        return serial(replayed_result(cached))
    if not getattr(request.app.state.db, "connected", True) and step not in {"dify_run", "mcp_call"} and not step.startswith("nutri_"):
        raise control_error(503, "DEPENDENCY_UNAVAILABLE",
                            request.app.state.db.schema_error or "数据库暂不可用，后台正在自动重连",
                            can_retry=True, operation_id=preview.operation_id)
    if not request.app.state.db.write_features.get("debug") and step not in {"dify_run", "mcp_call"} and not step.startswith("nutri_"):
        raise control_error(409, "WRITE_DISABLED",
                            request.app.state.db.schema_error or "debug database writes are disabled",
                            operation_id=preview.operation_id)
    run = await asyncio.to_thread(request.app.state.debug_store.get, run_id)
    if not run:
        raise control_error(409, "PREVIEW_STALE", "调试运行不存在，请重新预览",
                            requires_repreview=True, operation_id=preview.operation_id)
    target = str(intent.get("record_id", ""))
    preview, replayed, cached = request.app.state.previews.begin(body.preview_token, f"debug.{step}")
    if replayed:
        return serial(replayed_result(cached))
    op = preview.operation_id
    await write_started_audit(request, body.preview_token, f"debug.{step}", target, intent["reason"], op,
                              run_id=run_id)
    try:
        result = await request.app.state.debug.execute_step(run, intent)
        safe = redact(result)
        await asyncio.to_thread(request.app.state.debug_store.record, run_id, step, f"debug.{step}", "succeeded", safe)
        await request.app.state.audit.write(f"debug.{step}", target, intent["reason"], "succeeded", operation_id=op, result=safe)
        final = serial(safe)
        request.app.state.previews.succeed(body.preview_token, final)
        return final
    except Exception as exc:
        await asyncio.to_thread(request.app.state.debug_store.record, run_id, step, f"debug.{step}", "failed", {"error": str(exc)})
        await write_failed_audit(request, f"debug.{step}", target, intent["reason"], op, exc)
        request.app.state.previews.indeterminate(body.preview_token, str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "调试步骤结果无法确认，请通过操作编号检查审计和目标记录",
                            operation_id=op) from exc


@router.post("/api/debug/dify/run/preview")
async def dify_run_preview(request: Request, body: DebugStepRequest, run_id: str = Query(...)):
    return await step_preview(request, run_id, "dify_run", body)


@router.post("/api/debug/dify/run/execute")
async def dify_run_execute(request: Request, body: ExecuteRequest, run_id: str = Query(...)):
    return await step_execute(request, run_id, "dify_run", body)


@router.post("/api/debug/mcp/call/preview")
async def mcp_call_preview(request: Request, body: DebugStepRequest, run_id: str = Query(...)):
    return await step_preview(request, run_id, "mcp_call", body)


@router.post("/api/debug/mcp/call/execute")
async def mcp_call_execute(request: Request, body: ExecuteRequest, run_id: str = Query(...)):
    return await step_execute(request, run_id, "mcp_call", body)
