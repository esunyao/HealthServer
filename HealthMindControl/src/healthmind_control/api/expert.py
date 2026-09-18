from fastapi import APIRouter, HTTPException, Request

from ..models import ExecuteRequest, SqlPreviewRequest
from ..security import (
    control_error, redact, replayed_result, require_csrf, write_failed_audit, write_started_audit,
)
from ..util import serial

router = APIRouter()


def enabled(request: Request, check_database: bool = True) -> None:
    if not request.app.state.settings.enable_expert_mode:
        raise HTTPException(404, "expert mode is disabled")
    if not check_database:
        return
    if not getattr(request.app.state.db, "connected", True):
        raise control_error(503, "DEPENDENCY_UNAVAILABLE",
                            request.app.state.db.schema_error or "数据库暂不可用，后台正在自动重连",
                            can_retry=True)
    if not request.app.state.db.write_features.get("expert"):
        raise control_error(409, "WRITE_DISABLED",
                            request.app.state.db.schema_error or "expert SQL is disabled")


@router.post("/api/expert/sql/preview")
async def sql_preview(request: Request, body: SqlPreviewRequest):
    enabled(request)
    require_csrf(request, body.csrf_token)
    try:
        result = await request.app.state.expert.preview(body.sql)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    intent = body.model_dump(exclude={"preview_token", "confirmation"})
    token, preview = request.app.state.previews.create("expert.sql", intent, result)
    return serial({**redact(result), "preview_token": token, "expires_at": preview.expires_at,
                   "operation_id": preview.operation_id,
                   "confirmation": f"SQL {result['sha8']} {body.database}"})


@router.post("/api/expert/sql/execute")
async def sql_execute(request: Request, body: ExecuteRequest):
    enabled(request, check_database=False)
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.inspect(body.preview_token, "expert.sql")
    info = request.app.state.expert.analyze(preview.payload["sql"])
    expected = f"SQL {info['sha8']} {preview.payload['database']}"
    if body.confirmation != expected:
        raise control_error(409, "CONFIRMATION_MISMATCH", "确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(body.preview_token, "expert.sql")
    if replayed:
        return serial(replayed_result(cached))
    # Dependency and feature checks must happen while the token is still active.
    # A transient database outage therefore remains retryable with this preview.
    enabled(request)
    preview, replayed, cached = request.app.state.previews.begin(body.preview_token, "expert.sql")
    if replayed:
        return serial(replayed_result(cached))
    reason = preview.payload["reason"]
    op = preview.operation_id
    await write_started_audit(request, body.preview_token, "expert.sql", info["sha8"], reason, op,
                              statement_class=info["statement_class"], sql_sha256=info["sha256"])
    try:
        result = await request.app.state.expert.execute(preview.payload["sql"])
        await request.app.state.audit.write("expert.sql", info["sha8"], reason, "succeeded", operation_id=op,
                                            statement_class=info["statement_class"], row_count=result["row_count"])
        final = serial(redact(result))
        request.app.state.previews.succeed(body.preview_token, final)
        return final
    except Exception as exc:
        await write_failed_audit(request, "expert.sql", info["sha8"], reason, op, exc)
        request.app.state.previews.indeterminate(body.preview_token, str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "SQL 执行结果无法确认，请通过操作编号检查审计和目标记录",
                            operation_id=op) from exc
