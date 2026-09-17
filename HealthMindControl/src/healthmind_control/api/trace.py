from fastapi import APIRouter, Request

from ..security import redact, require_database_available
from ..util import serial

router = APIRouter()


@router.get("/api/traces/{identifier}")
async def trace(request: Request, identifier: str):
    require_database_available(request)
    result = await request.app.state.repo.trace(identifier)
    for stage in result.get("stages", []):
        stage["rows"] = redact(stage["rows"])
    return serial(result)
