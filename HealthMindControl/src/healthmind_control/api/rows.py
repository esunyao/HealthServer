from fastapi import APIRouter, HTTPException, Query, Request

from ..security import redact, require_database_available
from ..util import decode_cursor, serial

router = APIRouter()


@router.get("/api/rows/meta")
async def rows_meta(request: Request):
    require_database_available(request)
    return serial(await request.app.state.repo.rows_meta())


@router.get("/api/rows/{kind}")
async def list_rows(request: Request, kind: str, status: str | None = None, analysis: str | None = None,
                    code: str | None = None, service: str | None = None, subject_id: str | None = None,
                    since: str | None = None, until: str | None = None,
                    cursor: str | None = None, limit: int = Query(50, ge=1, le=100)):
    require_database_available(request)
    if cursor and decode_cursor(cursor) is None:
        raise HTTPException(400, "cursor 无效")
    try:
        return serial(await request.app.state.repo.list_rows(
            kind, status, analysis, code, service, subject_id, since, until, cursor, limit,
        ))
    except KeyError:
        raise HTTPException(404, "unknown row kind")


@router.get("/api/rows/{kind}/{row_id}")
async def row_detail(request: Request, kind: str, row_id: str):
    require_database_available(request)
    try:
        row = await request.app.state.repo.row_detail(kind, row_id)
    except KeyError:
        raise HTTPException(404, "unknown row kind")
    if not row:
        raise HTTPException(404, "row not found")
    return serial(redact(row))
