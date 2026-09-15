import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..util import serial

router = APIRouter()


@router.get("/api/events")
async def events(request: Request):
    """SSE：仅推送轻量摘要（status_light），昂贵数据由页面按需拉取。"""

    async def stream():
        queue = request.app.state.status_events.subscribe()
        try:
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"event: status\ndata: {json.dumps(serial(payload), ensure_ascii=False)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            request.app.state.status_events.unsubscribe(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
