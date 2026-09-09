from fastapi import APIRouter, HTTPException, Query, Request

from ..security import redact
from ..util import decode_cursor, serial

router = APIRouter()


@router.get("/api/tasks")
async def list_tasks(request: Request, status: str | None = None, task_type: str | None = None,
                     service: str | None = None, code: str | None = None, subject: str | None = None,
                     since: str | None = None, until: str | None = None,
                     cursor: str | None = None, limit: int = Query(50, ge=1, le=100)):
    if cursor and decode_cursor(cursor) is None:
        raise HTTPException(400, "cursor 无效")
    return serial(await request.app.state.repo.list_tasks(
        status, task_type, service, code, subject, since, until, cursor, limit,
    ))


@router.get("/api/tasks/{task_id}")
async def task_detail(request: Request, task_id: str):
    bundle = await request.app.state.repo.task_bundle(task_id)
    if bundle["task"] is None:
        raise HTTPException(404, "task not found")
    return serial(redact(bundle))
