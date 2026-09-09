from fastapi import APIRouter, HTTPException, Query, Request

from ..models import RecoveryRequest, RetryRequest
from ..security import redact, require_csrf, sha256_json
from ..util import serial

router = APIRouter()


def _snapshot_target(operation: str, schema: str) -> tuple[str, str]:
    if operation in {"reset_outbox", "replay_outbox"}:
        return (f"{schema}.integration_outbox", "event_id")
    if operation == "replay_nutri_inbox":
        return ("nutri.integration_inbox", "event_id")
    if operation == "replay_hm_inbox":
        return ("nutri.integration_outbox", "event_id")
    if operation == "recover_attempt":
        return ("healthmind.ai_task_attempts", "attempt_id")
    return ("healthmind.ai_tasks", "task_id")


# ---------------------------------------------------------------- 修复向导
@router.get("/api/repair/plan")
async def repair_plan(request: Request, query: str = Query(min_length=3, max_length=200)):
    return serial(await request.app.state.repo.repair_guide(query))


# ---------------------------------------------------------------- 克隆任务重试
@router.post("/api/tasks/{task_id}/retry/preview")
async def retry_preview(request: Request, task_id: str, body: RetryRequest):
    require_csrf(request, body.csrf_token)
    snapshot = await request.app.state.repo.snapshot("healthmind.ai_tasks", "task_id", task_id)
    if not snapshot:
        raise HTTPException(404, "task not found")
    validation = await request.app.state.repo.retry_validation(task_id)
    token, preview = request.app.state.previews.create(
        "task.retry", {**body.model_dump(), "task_id": task_id}, snapshot,
    )
    return {
        "preview_token": token, "expires_at": preview.expires_at,
        "snapshot": serial(redact(snapshot)),
        "validation": serial(redact(validation)),
        "confirmation": f"RETRY {task_id}",
    }


@router.post("/api/tasks/{task_id}/retry/execute")
async def retry_execute(request: Request, task_id: str, body: RetryRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.consume(body.preview_token or "", "task.retry")
    if body.confirmation != f"RETRY {task_id}":
        raise HTTPException(409, "confirmation text mismatch")
    current = await request.app.state.repo.snapshot("healthmind.ai_tasks", "task_id", task_id)
    if not current or sha256_json(current) != preview.snapshot_hash:
        raise HTTPException(409, "任务在预览后发生变化，请重新预览")
    op = request.app.state.audit.write("task.retry", task_id, body.reason, "started")
    try:
        new_id = await request.app.state.repo.retry_task(task_id, body.release_id, body.reason, op)
        request.app.state.audit.write("task.retry", task_id, body.reason, "succeeded", operation_id=op, new_task_id=new_id)
        return {"task_id": new_id}
    except Exception as exc:
        request.app.state.audit.write("task.retry", task_id, body.reason, "failed", operation_id=op, error=str(exc))
        raise


# ---------------------------------------------------------------- 受控修复预览
@router.post("/api/recovery/preview")
async def recovery_preview(request: Request, body: RecoveryRequest):
    require_csrf(request, body.csrf_token)
    if body.operation == "replay_hm_inbox":
        # 特殊预检：只有“published 且收件箱缺失且无任务”才可重放
        try:
            message = await request.app.state.repo.hm_capture_ready_message(body.record_id)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        snapshot = await request.app.state.repo.snapshot("nutri.integration_outbox", "event_id", body.record_id)
        if not snapshot:
            raise HTTPException(404, "record not found")
        token, preview = request.app.state.previews.create(
            "recovery.replay_hm_inbox", body.model_dump(exclude={"preview_token"}), snapshot,
        )
        return {
            "preview_token": token, "expires_at": preview.expires_at,
            "snapshot": serial(redact(snapshot)), "confirmation": f"RECOVER {body.record_id}",
            "message": serial(redact({"topic": message["topic"], "key": message["key"]})),
        }
    if body.operation == "recover_attempt":
        # 自定义快照：attempt + 其任务行（含 lock_version），双字段绑定防状态漂移
        attempt = await request.app.state.repo.snapshot("healthmind.ai_task_attempts", "attempt_id", body.record_id)
        if not attempt:
            raise HTTPException(404, "attempt not found")
        task = await request.app.state.repo.snapshot("healthmind.ai_tasks", "task_id", str(attempt["task_id"]))
        snapshot = {"attempt": attempt, "task": task}
        token, preview = request.app.state.previews.create(
            "recovery.recover_attempt", body.model_dump(exclude={"preview_token"}), snapshot,
        )
        return {
            "preview_token": token, "expires_at": preview.expires_at,
            "snapshot": serial(redact(snapshot)),
            "expected_lock_version": task["lock_version"] if task else None,
            "confirmation": f"RECOVER {body.record_id}",
        }
    table, column = _snapshot_target(body.operation, body.schema_name)
    snapshot = await request.app.state.repo.snapshot(table, column, body.record_id)
    if not snapshot:
        raise HTTPException(404, "record not found")
    token, preview = request.app.state.previews.create(
        "recovery." + body.operation, body.model_dump(exclude={"preview_token"}), snapshot,
    )
    return {
        "preview_token": token, "expires_at": preview.expires_at,
        "snapshot": serial(redact(snapshot)), "confirmation": f"RECOVER {body.record_id}",
    }


# ---------------------------------------------------------------- 受控修复执行
@router.post("/api/recovery/execute")
async def recovery_execute(request: Request, body: RecoveryRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.consume(body.preview_token or "", "recovery." + body.operation)
    if body.confirmation != f"RECOVER {body.record_id}":
        raise HTTPException(409, "confirmation text mismatch")

    if body.operation == "replay_hm_inbox":
        current = await request.app.state.repo.snapshot("nutri.integration_outbox", "event_id", body.record_id)
        if not current or sha256_json(current) != preview.snapshot_hash:
            raise HTTPException(409, "记录在预览后发生变化，请重新预览")
    elif body.operation == "recover_attempt":
        attempt = await request.app.state.repo.snapshot("healthmind.ai_task_attempts", "attempt_id", body.record_id)
        task = await request.app.state.repo.snapshot("healthmind.ai_tasks", "task_id", str(attempt["task_id"])) if attempt else None
        current = {"attempt": attempt, "task": task}
        if not attempt or sha256_json(current) != preview.snapshot_hash:
            raise HTTPException(409, "记录在预览后发生变化，请重新预览")
    else:
        table, column = _snapshot_target(body.operation, body.schema_name)
        current = await request.app.state.repo.snapshot(table, column, body.record_id)
        if not current or sha256_json(current) != preview.snapshot_hash:
            raise HTTPException(409, "记录在预览后发生变化，请重新预览")

    op = request.app.state.audit.write("recovery." + body.operation, body.record_id, body.reason, "started")
    try:
        if body.operation in {"replay_outbox", "replay_nutri_inbox", "replay_hm_inbox"}:
            if body.operation == "replay_hm_inbox":
                message = await request.app.state.repo.hm_capture_ready_message(body.record_id)
            else:
                message = await request.app.state.repo.replay_message(
                    body.schema_name, body.record_id, body.operation == "replay_nutri_inbox",
                )
            result = await request.app.state.kafka.produce(
                message["topic"], message["key"], message["payload"], {"x-healthmind-control-replay": "true"}, None,
            )
        else:
            result = await request.app.state.repo.recover(
                body.operation, body.schema_name, body.record_id, body.expected_lock_version,
            )
        request.app.state.audit.write(
            "recovery." + body.operation, body.record_id, body.reason, "succeeded", operation_id=op, result=result,
        )
        return serial(result)
    except Exception as exc:
        request.app.state.audit.write(
            "recovery." + body.operation, body.record_id, body.reason, "failed", operation_id=op, error=str(exc),
        )
        raise
