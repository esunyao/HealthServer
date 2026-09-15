from fastapi import APIRouter, HTTPException, Request

from ..models import ExecuteRequest, SqlPreviewRequest
from ..security import redact, require_csrf
from ..util import serial

router = APIRouter()


def enabled(request: Request) -> None:
    if not request.app.state.settings.enable_expert_mode:
        raise HTTPException(404, "expert mode is disabled")
    if not request.app.state.db.write_features.get("expert"):
        raise HTTPException(409, request.app.state.db.schema_error or "expert SQL is disabled")


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
                   "confirmation": f"SQL {result['sha8']} {body.database}"})


@router.post("/api/expert/sql/execute")
async def sql_execute(request: Request, body: ExecuteRequest):
    enabled(request)
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.consume(body.preview_token, "expert.sql")
    info = request.app.state.expert.analyze(preview.payload["sql"])
    expected = f"SQL {info['sha8']} {preview.payload['database']}"
    if body.confirmation != expected:
        raise HTTPException(409, "confirmation text mismatch")
    reason = preview.payload["reason"]
    op = request.app.state.audit.write("expert.sql", info["sha8"], reason, "started",
                                       statement_class=info["statement_class"], sql_sha256=info["sha256"])
    try:
        result = await request.app.state.expert.execute(preview.payload["sql"])
        request.app.state.audit.write("expert.sql", info["sha8"], reason, "succeeded", operation_id=op,
                                      statement_class=info["statement_class"], row_count=result["row_count"])
        return serial(redact(result))
    except Exception as exc:
        request.app.state.audit.write("expert.sql", info["sha8"], reason, "failed", operation_id=op, error=str(exc))
        raise
