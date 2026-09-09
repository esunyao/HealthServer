import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..config import settings
from ..util import serial

router = APIRouter()


@router.get("/api/events")
async def events(request: Request):
    """SSE：仅推送轻量摘要（status_light），昂贵数据由页面按需拉取。"""

    async def stream():
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await request.app.state.repo.status_light()
            except Exception as exc:
                payload = {"error": str(exc)}
            yield f"event: status\ndata: {json.dumps(serial(payload), ensure_ascii=False)}\n\n"
            await asyncio.sleep(settings.refresh_seconds)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
