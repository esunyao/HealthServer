"""Unauthenticated database liveness endpoint."""

import asyncio
from fastapi import APIRouter, HTTPException, Request
from ...observability import log_event, log_exception

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
async def healthz(request: Request) -> dict[str, str]:
    try:
        ready = await asyncio.to_thread(
            request.app.state.runtime.repository.health_check
        )
    except Exception as exception:
        ready = False
        if not request.app.state.health_failure_logged:
            request.app.state.health_failure_logged = True
            log_exception("healthz.database_unavailable", exception, level="WARNING")
        else:
            log_event(
                "healthz.database_unavailable",
                level="DEBUG",
                error_type=type(exception).__name__,
            )
    if not ready:
        if not request.app.state.health_failure_logged:
            request.app.state.health_failure_logged = True
            log_event(
                "healthz.database_unavailable",
                level="WARNING",
                message="Database health check returned false",
            )
        raise HTTPException(status_code=503, detail="Database unavailable")
    request.app.state.health_failure_logged = False
    return {"status": "ok"}
