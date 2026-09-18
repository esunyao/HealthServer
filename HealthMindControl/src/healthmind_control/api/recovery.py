from fastapi import APIRouter, HTTPException, Query, Request

from ..models import ExecuteRequest, RecoveryRequest, RetryRequest
from ..security import (
    control_error, redact, replayed_result, require_csrf, require_database_available, sha256_json,
    write_failed_audit, write_started_audit,
)
from ..util import serial

router = APIRouter()


def _require_recovery_writes(request: Request, operation_id: str | None = None) -> None:
    if not getattr(request.app.state.db, "connected", True):
        raise control_error(503, "DEPENDENCY_UNAVAILABLE",
                            request.app.state.db.schema_error or "数据库暂不可用，后台正在自动重连",
                            can_retry=True, operation_id=operation_id)
    if not request.app.state.db.write_features.get("recovery"):
        raise control_error(409, "WRITE_DISABLED",
                            request.app.state.db.schema_error or "recovery writes are disabled",
                            operation_id=operation_id)


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
    require_database_available(request)
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
        "preview_token": token, "expires_at": preview.expires_at, "operation_id": preview.operation_id,
        "snapshot": serial(redact(snapshot)),
        "validation": serial(redact(validation)),
        "confirmation": f"RETRY {task_id}",
    }


@router.post("/api/tasks/{task_id}/retry/execute")
async def retry_execute(request: Request, task_id: str, body: ExecuteRequest):
    require_csrf(request, body.csrf_token)
    token = body.preview_token or ""
    preview = request.app.state.previews.inspect(token, "task.retry")
    intent = preview.payload
    if intent.get("task_id") != task_id:
        raise control_error(409, "PREVIEW_TARGET_MISMATCH", "预览目标不匹配",
                            requires_repreview=True, operation_id=preview.operation_id)
    if body.confirmation != f"RETRY {task_id}":
        raise control_error(409, "CONFIRMATION_MISMATCH", "确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(token, "task.retry")
    if replayed:
        return replayed_result(cached)
    _require_recovery_writes(request, preview.operation_id)
    current = await request.app.state.repo.snapshot("healthmind.ai_tasks", "task_id", task_id)
    if not current or sha256_json(current) != preview.snapshot_hash:
        raise control_error(409, "PREVIEW_STALE", "任务在预览后发生变化，请重新预览",
                            requires_repreview=True, operation_id=preview.operation_id)
    reason = str(intent["reason"])
    preview, replayed, cached = request.app.state.previews.begin(token, "task.retry")
    if replayed:
        return replayed_result(cached)
    op = preview.operation_id
    await write_started_audit(request, token, "task.retry", task_id, reason, op)
    try:
        new_id = await request.app.state.repo.retry_task(task_id, intent.get("release_id"), reason, op)
        await request.app.state.audit.write("task.retry", task_id, reason, "succeeded", operation_id=op, new_task_id=new_id)
        result = {"task_id": new_id}
        request.app.state.previews.succeed(token, result)
        return result
    except Exception as exc:
        await write_failed_audit(request, "task.retry", task_id, reason, op, exc)
        request.app.state.previews.indeterminate(token, str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "任务克隆结果无法确认，请通过操作编号检查审计和目标记录",
                            operation_id=op) from exc


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
            "preview_token": token, "expires_at": preview.expires_at, "operation_id": preview.operation_id,
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
        intent = body.model_dump(exclude={"preview_token", "confirmation"})
        intent["expected_lock_version"] = task["lock_version"] if task else None
        token, preview = request.app.state.previews.create("recovery.recover_attempt", intent, snapshot)
        return {
            "preview_token": token, "expires_at": preview.expires_at, "operation_id": preview.operation_id,
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
        "preview_token": token, "expires_at": preview.expires_at, "operation_id": preview.operation_id,
        "snapshot": serial(redact(snapshot)), "confirmation": f"RECOVER {body.record_id}",
    }


# ---------------------------------------------------------------- 受控修复执行
@router.post("/api/recovery/execute")
async def recovery_execute(request: Request, body: ExecuteRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.inspect(body.preview_token, "recovery.", prefix=True)
    intent = RecoveryRequest.model_validate(preview.payload)
    if body.confirmation != f"RECOVER {intent.record_id}":
        raise control_error(409, "CONFIRMATION_MISMATCH", "确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(
        body.preview_token, "recovery.", prefix=True,
    )
    if replayed:
        return serial(replayed_result(cached))
    _require_recovery_writes(request, preview.operation_id)

    if intent.operation == "replay_hm_inbox":
        current = await request.app.state.repo.snapshot("nutri.integration_outbox", "event_id", intent.record_id)
        if not current or sha256_json(current) != preview.snapshot_hash:
            raise control_error(409, "PREVIEW_STALE", "记录在预览后发生变化，请重新预览",
                                requires_repreview=True, operation_id=preview.operation_id)
    elif intent.operation == "recover_attempt":
        attempt = await request.app.state.repo.snapshot("healthmind.ai_task_attempts", "attempt_id", intent.record_id)
        task = await request.app.state.repo.snapshot("healthmind.ai_tasks", "task_id", str(attempt["task_id"])) if attempt else None
        current = {"attempt": attempt, "task": task}
        if not attempt or sha256_json(current) != preview.snapshot_hash:
            raise control_error(409, "PREVIEW_STALE", "记录在预览后发生变化，请重新预览",
                                requires_repreview=True, operation_id=preview.operation_id)
    else:
        table, column = _snapshot_target(intent.operation, intent.schema_name)
        current = await request.app.state.repo.snapshot(table, column, intent.record_id)
        if not current or sha256_json(current) != preview.snapshot_hash:
            raise control_error(409, "PREVIEW_STALE", "记录在预览后发生变化，请重新预览",
                                requires_repreview=True, operation_id=preview.operation_id)

    preview, replayed, cached = request.app.state.previews.begin(
        body.preview_token, "recovery.", prefix=True,
    )
    if replayed:
        return serial(replayed_result(cached))
    op = preview.operation_id
    await write_started_audit(request, body.preview_token, "recovery." + intent.operation,
                              intent.record_id, intent.reason, op)
    try:
        if intent.operation in {"replay_outbox", "replay_nutri_inbox", "replay_hm_inbox"}:
            if intent.operation == "replay_hm_inbox":
                message = await request.app.state.repo.hm_capture_ready_message(intent.record_id)
            else:
                message = await request.app.state.repo.replay_message(
                    intent.schema_name, intent.record_id, intent.operation == "replay_nutri_inbox",
                )
            result = await request.app.state.kafka.produce(
                message["topic"], message["key"], message["payload"], {"x-healthmind-control-replay": "true"}, None,
            )
        else:
            result = await request.app.state.repo.recover(
                intent.operation, intent.schema_name, intent.record_id, intent.expected_lock_version,
            )
        await request.app.state.audit.write(
            "recovery." + intent.operation, intent.record_id, intent.reason, "succeeded", operation_id=op, result=result,
        )
        final = serial(result)
        request.app.state.previews.succeed(body.preview_token, final)
        return final
    except Exception as exc:
        await write_failed_audit(request, "recovery." + intent.operation, intent.record_id, intent.reason, op, exc)
        request.app.state.previews.indeterminate(body.preview_token, str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "修复结果无法确认，请通过操作编号检查审计和目标记录",
                            operation_id=op) from exc
