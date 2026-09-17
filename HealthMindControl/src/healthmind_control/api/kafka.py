from fastapi import APIRouter, HTTPException, Request

from ..models import ExecuteRequest, KafkaOffsetRequest, KafkaProduceRequest
from ..security import (
    canonical_json, control_error, redact, replayed_result, require_csrf,
    write_failed_audit, write_started_audit,
)
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
        "preview_token": token, "expires_at": preview.expires_at, "operation_id": preview.operation_id,
        "warnings": warnings,
        "requires_force": bool(warnings), "confirmation": f"PRODUCE {body.topic}",
        "payload_sha256": __import__("hashlib").sha256(body.payload_text.encode("utf-8")).hexdigest(),
        "canonical_sha256": __import__("hashlib").sha256(canonical_json(payload).encode("utf-8")).hexdigest(),
        "bytes": len(body.payload_text.encode("utf-8")),
    }


@router.post("/api/kafka/produce/execute")
async def produce_execute(request: Request, body: ExecuteRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.inspect(body.preview_token or "", "kafka.produce")
    intent = preview.payload
    topic = str(intent["topic"])
    if body.confirmation != f"PRODUCE {topic}":
        raise control_error(409, "CONFIRMATION_MISMATCH", "确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    payload = request.app.state.kafka.parse_payload(str(intent["payload_text"]))
    warnings = request.app.state.kafka.validate_event(topic, payload)
    if warnings and not body.accept_warnings:
        raise control_error(409, "WARNINGS_NOT_ACCEPTED", "存在校验警告，请确认后再执行", can_retry=True,
                            operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(body.preview_token or "", "kafka.produce")
    if replayed:
        return replayed_result(cached)
    try:
        metadata = await request.app.state.kafka.metadata(force=True)
    except Exception as exc:
        raise control_error(503, "DEPENDENCY_UNAVAILABLE", f"Kafka 暂不可用: {exc}", can_retry=True,
                            operation_id=preview.operation_id) from exc
    if topic not in {item["name"] for item in metadata.get("topics", [])}:
        raise control_error(409, "PREVIEW_STALE", "目标 topic 在预览后已不存在",
                            requires_repreview=True, operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.begin(body.preview_token or "", "kafka.produce")
    if replayed:
        return replayed_result(cached)
    op = preview.operation_id
    write_started_audit(
        request, body.preview_token or "", "kafka.produce", topic, str(intent["reason"]), op,
        payload_sha256=__import__("hashlib").sha256(str(intent["payload_text"]).encode("utf-8")).hexdigest(),
    )
    try:
        result = await request.app.state.kafka.produce(topic, intent.get("key"), str(intent["payload_text"]), intent.get("headers", {}), intent.get("partition"))
        request.app.state.audit.write("kafka.produce", topic, str(intent["reason"]), "succeeded", operation_id=op, result=result)
        request.app.state.previews.succeed(body.preview_token or "", result)
        return result
    except Exception as exc:
        write_failed_audit(request, "kafka.produce", topic, str(intent["reason"]), op, exc)
        request.app.state.previews.indeterminate(body.preview_token or "", str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "Kafka 交付结果无法确认，请通过操作编号检查审计和目标 topic",
                            operation_id=op) from exc


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
    return {"preview_token": token, "expires_at": preview.expires_at,
            "operation_id": preview.operation_id, "plan": plan,
            "confirmation": f"OFFSET {body.group_id} {body.topic}"}


@router.post("/api/kafka/offsets/execute")
async def offset_execute(request: Request, body: ExecuteRequest):
    if not request.app.state.settings.enable_expert_mode:
        raise HTTPException(404, "expert mode is disabled")
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.inspect(body.preview_token, "kafka.offset")
    plan, reason = preview.payload["plan"], preview.payload["reason"]
    if body.confirmation != f"OFFSET {plan['group_id']} {plan['topic']}":
        raise control_error(409, "CONFIRMATION_MISMATCH", "确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(body.preview_token, "kafka.offset")
    if replayed:
        return replayed_result(cached)
    try:
        fresh = await request.app.state.kafka.offset_plan(
            plan["group_id"], plan["topic"], plan["partition"], "absolute", plan["target"],
        )
    except Exception as exc:
        raise control_error(503, "DEPENDENCY_UNAVAILABLE", f"Kafka offset 预检失败: {exc}", can_retry=True,
                            operation_id=preview.operation_id) from exc
    if fresh["current"] != plan["current"]:
        raise control_error(409, "PREVIEW_STALE", "消费组 offset 在预览后发生变化",
                            requires_repreview=True, operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.begin(body.preview_token, "kafka.offset")
    if replayed:
        return replayed_result(cached)
    op = preview.operation_id
    write_started_audit(request, body.preview_token, "kafka.offset", plan["group_id"], reason, op, before=plan)
    try:
        result = await request.app.state.kafka.alter_offset(plan)
        request.app.state.audit.write("kafka.offset", plan["group_id"], reason, "succeeded", operation_id=op, result=result)
        request.app.state.previews.succeed(body.preview_token, result)
        return result
    except Exception as exc:
        write_failed_audit(request, "kafka.offset", plan["group_id"], reason, op, exc)
        request.app.state.previews.indeterminate(body.preview_token, str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "消费组 offset 修改结果无法确认，请通过操作编号检查",
                            operation_id=op) from exc
