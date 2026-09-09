from fastapi import APIRouter, HTTPException, Request

from ..models import KafkaProduceRequest
from ..security import redact, require_csrf, sha256_json
from ..util import serial

router = APIRouter()


@router.get("/api/kafka/topics")
async def topics(request: Request, force: bool = False):
    return await request.app.state.kafka.metadata(force=force)


@router.get("/api/kafka/groups")
async def groups(request: Request):
    return await request.app.state.kafka.groups()


@router.get("/api/kafka/messages")
async def messages(request: Request, topic: str, partition: int = 0, start: str = "latest",
                   offset: int | None = None, time_ms: int | None = None, limit: int = 50,
                   key: str | None = None, event_id: str | None = None, trace_id: str | None = None,
                   event_type: str | None = None, contains: str | None = None, max_scan: int | None = None):
    if start not in ("latest", "earliest", "offset", "time"):
        raise HTTPException(400, "start 取值应为 latest/earliest/offset/time")
    if start == "time" and time_ms is None:
        raise HTTPException(400, "start=time 需要 time_ms")
    if start == "offset" and offset is None:
        raise HTTPException(400, "start=offset 需要 offset")
    return redact(await request.app.state.kafka.messages(
        topic, partition, start, offset, time_ms, limit, key, event_id, trace_id, event_type, contains, max_scan,
    ))


@router.post("/api/kafka/produce/preview")
async def produce_preview(request: Request, body: KafkaProduceRequest):
    require_csrf(request, body.csrf_token)
    metadata = await request.app.state.kafka.metadata()
    if body.topic not in {t["name"] for t in metadata["topics"]}:
        raise HTTPException(404, "topic does not exist")
    warnings = request.app.state.kafka.validate_event(body.topic, body.payload)
    token, preview = request.app.state.previews.create(
        "kafka.produce", body.model_dump(exclude={"preview_token"}),
        {"topic": body.topic, "payload": body.payload},
    )
    return {
        "preview_token": token, "expires_at": preview.expires_at, "warnings": warnings,
        "requires_force": bool(warnings), "confirmation": f"PRODUCE {body.topic}",
        "payload_sha256": sha256_json(body.payload),
    }


@router.post("/api/kafka/produce/execute")
async def produce_execute(request: Request, body: KafkaProduceRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.consume(body.preview_token or "", "kafka.produce")
    if body.confirmation != f"PRODUCE {body.topic}":
        raise HTTPException(409, "confirmation text mismatch")
    warnings = request.app.state.kafka.validate_event(body.topic, body.payload)
    if warnings and not body.force:
        raise HTTPException(409, "validation warnings require force=true")
    op = request.app.state.audit.write(
        "kafka.produce", body.topic, body.reason, "started", payload_sha256=sha256_json(body.payload),
    )
    try:
        result = await request.app.state.kafka.produce(body.topic, body.key, body.payload, body.headers, body.partition)
        request.app.state.audit.write("kafka.produce", body.topic, body.reason, "succeeded", operation_id=op, result=result)
        return result
    except Exception as exc:
        request.app.state.audit.write("kafka.produce", body.topic, body.reason, "failed", operation_id=op, error=str(exc))
        raise
