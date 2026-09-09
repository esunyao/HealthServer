from fastapi import APIRouter, Query, Request

from ..util import serial

router = APIRouter()


@router.get("/api/audit/actions")
async def audit_actions(request: Request, limit: int = Query(200, ge=1, le=1000),
                        action: str | None = None, outcome: str | None = None,
                        operation_id: str | None = None):
    """读取本机操作审计 JSONL（倒序）。"""
    return serial(request.app.state.audit.tail(limit, action, outcome, operation_id))
