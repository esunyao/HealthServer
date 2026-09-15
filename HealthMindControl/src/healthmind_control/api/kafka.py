from fastapi import APIRouter, HTTPException, Request

from ..models import ExecuteRequest, KafkaOffsetRequest, KafkaProduceRequest
from ..security import canonical_json, redact, require_csrf
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
    try:
        payload = request.app.state.kafka.parse_payload(body.payload_text)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    warnings = request.app.state.kafka.validate_event(body.topic, payload)
    intent = body.model_dump(exclude={"preview_token", "confirmation"})
    token, preview = request.app.state.previews.create(
        "kafka.produce", intent, {"topic": body.topic, "payload_text": body.payload_text},
    )
    return {
        "preview_token": token, "expires_at": preview.expires_at, "warnings": warnings,
        "requires_force": bool(warnings), "confirmation": f"PRODUCE {body.topic}",
        "payload_sha256": __import__("hashlib").sha256(body.payload_text.encode("utf-8")).hexdigest(),
        "canonical_sha256": __import__("hashlib").sha256(canonical_json(payload).encode("utf-8")).hexdigest(),
        "bytes": len(body.payload_text.encode("utf-8")),
    }


@router.post("/api/kafka/produce/execute")
async def produce_execute(request: Request, body: ExecuteRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.consume(body.preview_token or "", "kafka.produce")
    intent = preview.payload
    topic = str(intent["topic"])
    if body.confirmation != f"PRODUCE {topic}":
        raise HTTPException(409, "confirmation text mismatch")
    payload = request.app.state.kafka.parse_payload(str(intent["payload_text"]))
    warnings = request.app.state.kafka.validate_event(topic, payload)
    if warnings and not body.accept_warnings:
        raise HTTPException(409, "validation warnings require accept_warnings=true")
    op = request.app.state.audit.write(
        "kafka.produce", topic, str(intent["reason"]), "started",
        payload_sha256=__import__("hashlib").sha256(str(intent["payload_text"]).encode("utf-8")).hexdigest(),
    )
    try:
        result = await request.app.state.kafka.produce(topic, intent.get("key"), str(intent["payload_text"]), intent.get("headers", {}), intent.get("partition"))
        request.app.state.audit.write("kafka.produce", topic, str(intent["reason"]), "succeeded", operation_id=op, result=result)
        return result
    except Exception as exc:
        request.app.state.audit.write("kafka.produce", topic, str(intent["reason"]), "failed", operation_id=op, error=str(exc))
        raise


@router.post("/api/kafka/offsets/preview")
async def offset_preview(request: Request, body: KafkaOffsetRequest):
    if not request.app.state.settings.enable_expert_mode:
        raise HTTPException(404, "expert mode is disabled")
    require_csrf(request, body.csrf_token)
    try:
        plan = await request.app.state.kafka.offset_plan(
            body.group_id, body.topic, body.partition, body.position, body.value,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc))
    intent = {"plan": plan, "reason": body.reason}
    token, preview = request.app.state.previews.create("kafka.offset", intent, plan)
    return {"preview_token": token, "expires_at": preview.expires_at, "plan": plan,
            "confirmation": f"OFFSET {body.group_id} {body.topic}"}


@router.post("/api/kafka/offsets/execute")
async def offset_execute(request: Request, body: ExecuteRequest):
    if not request.app.state.settings.enable_expert_mode:
        raise HTTPException(404, "expert mode is disabled")
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.consume(body.preview_token, "kafka.offset")
    plan, reason = preview.payload["plan"], preview.payload["reason"]
    if body.confirmation != f"OFFSET {plan['group_id']} {plan['topic']}":
        raise HTTPException(409, "confirmation text mismatch")
    op = request.app.state.audit.write("kafka.offset", plan["group_id"], reason, "started", before=plan)
    try:
        result = await request.app.state.kafka.alter_offset(plan)
        request.app.state.audit.write("kafka.offset", plan["group_id"], reason, "succeeded", operation_id=op, result=result)
        return result
    except Exception as exc:
        request.app.state.audit.write("kafka.offset", plan["group_id"], reason, "failed", operation_id=op, error=str(exc))
        raise
