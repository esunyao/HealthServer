import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .audit import AuditLog
from .config import ROOT, settings
from .database import Database
from .dify import DifyService
from .kafka import KafkaService
from .models import KafkaProduceRequest, RecoveryRequest, ReleaseRequest, RetryRequest
from .repository import Repository
from .security import PreviewStore, redact, require_csrf, sha256_json


PACKAGE = Path(__file__).parent


def serial(value: Any) -> Any:
    return jsonable_encoder(value, custom_encoder={bytes: lambda v: v.decode("utf-8", "replace")})


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.csrf_token = secrets.token_urlsafe(32)
    app.state.previews = PreviewStore(settings.preview_ttl_seconds)
    app.state.audit = AuditLog(settings.audit_path)
    app.state.db = Database(settings)
    await app.state.db.open()
    app.state.repo = Repository(app.state.db, settings.stale_minutes, settings.task_retention_days)
    app.state.kafka = KafkaService(settings)
    app.state.dify = DifyService(settings)
    yield
    await app.state.db.close()


app = FastAPI(title="HealthMindControl", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
templates = Jinja2Templates(directory=PACKAGE / "templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"csrf_token": request.app.state.csrf_token, "refresh": settings.refresh_seconds})


@app.get("/api/status")
async def status(request: Request):
    repo_status, kafka_status, dify, mcp, auth = await asyncio.gather(
        request.app.state.repo.status(),
        request.app.state.kafka.metadata(),
        request.app.state.dify.probe(f"{settings.dify_url.rstrip('/')}/v1/info", True),
        request.app.state.dify.probe(settings.mcp_url, True),
        request.app.state.dify.probe(f"{settings.auth_url.rstrip('/')}/application/o/healthmind-mcp/.well-known/openid-configuration"),
        return_exceptions=True,
    )
    def safe(value): return {"ok": False, "error": str(value)} if isinstance(value, Exception) else value
    return serial({**safe(repo_status), "kafka": safe(kafka_status), "dify": safe(dify), "mcp": safe(mcp), "auth": safe(auth)})


@app.get("/api/backlogs")
async def backlogs(request: Request): return serial(await request.app.state.repo.backlogs())


@app.get("/api/tasks")
async def tasks(request: Request, status: str | None = None, cursor: str | None = None, limit: int = Query(50, ge=1, le=100)):
    return serial(await request.app.state.repo.tasks(status, cursor, limit))


@app.get("/api/traces/{identifier}")
async def trace(request: Request, identifier: str): return serial(redact(await request.app.state.repo.trace(identifier)))


@app.get("/api/kafka/topics")
async def topics(request: Request): return await request.app.state.kafka.metadata()


@app.get("/api/kafka/groups")
async def groups(request: Request): return await request.app.state.kafka.groups()


@app.get("/api/kafka/messages")
async def messages(request: Request, topic: str, partition: int = 0, start: str = "latest", offset: int | None = None, limit: int = 50, contains: str | None = None):
    return redact(await request.app.state.kafka.messages(topic, partition, start, offset, limit, contains))


@app.post("/api/kafka/produce/preview")
async def produce_preview(request: Request, body: KafkaProduceRequest):
    require_csrf(request, body.csrf_token)
    metadata = await request.app.state.kafka.metadata()
    if body.topic not in {t["name"] for t in metadata["topics"]}: raise HTTPException(404, "topic does not exist")
    warnings = request.app.state.kafka.validate_event(body.topic, body.payload)
    token, preview = request.app.state.previews.create("kafka.produce", body.model_dump(exclude={"preview_token"}), {"topic": body.topic, "payload": body.payload})
    return {"preview_token": token, "expires_at": preview.expires_at, "warnings": warnings, "requires_force": bool(warnings), "confirmation": f"PRODUCE {body.topic}", "payload_sha256": sha256_json(body.payload)}


@app.post("/api/kafka/produce/execute")
async def produce_execute(request: Request, body: KafkaProduceRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.consume(body.preview_token or "", "kafka.produce")
    if body.confirmation != f"PRODUCE {body.topic}": raise HTTPException(409, "confirmation text mismatch")
    warnings = request.app.state.kafka.validate_event(body.topic, body.payload)
    if warnings and not body.force: raise HTTPException(409, "validation warnings require force=true")
    op = request.app.state.audit.write("kafka.produce", body.topic, body.reason, "started", payload_sha256=sha256_json(body.payload))
    try:
        result = await request.app.state.kafka.produce(body.topic, body.key, body.payload, body.headers, body.partition)
        request.app.state.audit.write("kafka.produce", body.topic, body.reason, "succeeded", operation_id=op, result=result)
        return result
    except Exception as exc:
        request.app.state.audit.write("kafka.produce", body.topic, body.reason, "failed", operation_id=op, error=str(exc)); raise


@app.get("/api/releases")
async def releases(request: Request): return serial(await request.app.state.repo.releases())


@app.get("/api/dify/discover")
async def dify_discover(request: Request, app_id: str | None = None): return await request.app.state.dify.discover(app_id)


@app.get("/api/dify/published/{app_id}")
async def dify_published(request: Request, app_id: str): return await request.app.state.dify.published(app_id)


def release_snapshot(body: ReleaseRequest) -> dict[str, Any]:
    return {"operation": body.operation, "release_id": body.release_id, "workflow_id": body.workflow_id, "workflow_version": body.workflow_version, "release_version": body.release_version}


@app.post("/api/releases/preview")
async def release_preview(request: Request, body: ReleaseRequest):
    require_csrf(request, body.csrf_token)
    if body.operation == "create":
        required = [body.release_version, body.workspace_id, body.app_id, body.workflow_id, body.workflow_version, body.input_schema, body.output_schema]
        if any(v is None for v in required): raise HTTPException(422, "create requires all Dify IDs, version and schemas")
        snapshot = release_snapshot(body)
    else:
        if not body.release_id: raise HTTPException(422, "release_id required")
        snapshot = await request.app.state.repo.snapshot("healthmind.workflow_releases", "release_id", body.release_id)
        if not snapshot: raise HTTPException(404, "release not found")
    token, preview = request.app.state.previews.create("release."+body.operation, body.model_dump(exclude={"preview_token"}), snapshot)
    return {"preview_token": token, "expires_at": preview.expires_at, "snapshot": serial(snapshot), "confirmation": f"RELEASE {body.operation.upper()}"}


@app.post("/api/releases/execute")
async def release_execute(request: Request, body: ReleaseRequest):
    require_csrf(request, body.csrf_token); request.app.state.previews.consume(body.preview_token or "", "release."+body.operation)
    if body.confirmation != f"RELEASE {body.operation.upper()}": raise HTTPException(409, "confirmation text mismatch")
    op = request.app.state.audit.write("release."+body.operation, body.release_id or body.release_version or "new", body.reason, "started")
    try:
        if body.operation == "create": rid = await request.app.state.repo.create_release(body.model_dump(), body.reason)
        else: rid = body.release_id; await request.app.state.repo.transition_release(rid, body.operation, body.reason)
        request.app.state.audit.write("release."+body.operation, rid, body.reason, "succeeded", operation_id=op)
        return {"release_id": rid, "status": "ok"}
    except Exception as exc:
        request.app.state.audit.write("release."+body.operation, body.release_id or "new", body.reason, "failed", operation_id=op, error=str(exc)); raise


@app.post("/api/tasks/{task_id}/retry/preview")
async def retry_preview(request: Request, task_id: str, body: RetryRequest):
    require_csrf(request, body.csrf_token)
    snapshot = await request.app.state.repo.snapshot("healthmind.ai_tasks", "task_id", task_id)
    if not snapshot: raise HTTPException(404, "task not found")
    token, preview = request.app.state.previews.create("task.retry", {**body.model_dump(), "task_id": task_id}, snapshot)
    return {"preview_token": token, "expires_at": preview.expires_at, "snapshot": serial(redact(snapshot)), "confirmation": f"RETRY {task_id}"}


@app.post("/api/tasks/{task_id}/retry/execute")
async def retry_execute(request: Request, task_id: str, body: RetryRequest):
    require_csrf(request, body.csrf_token); request.app.state.previews.consume(body.preview_token or "", "task.retry")
    if body.confirmation != f"RETRY {task_id}": raise HTTPException(409, "confirmation text mismatch")
    op = request.app.state.audit.write("task.retry", task_id, body.reason, "started")
    try:
        new_id = await request.app.state.repo.retry_task(task_id, body.release_id, body.reason, op)
        request.app.state.audit.write("task.retry", task_id, body.reason, "succeeded", operation_id=op, new_task_id=new_id)
        return {"task_id": new_id}
    except Exception as exc:
        request.app.state.audit.write("task.retry", task_id, body.reason, "failed", operation_id=op, error=str(exc)); raise


@app.post("/api/recovery/preview")
async def recovery_preview(request: Request, body: RecoveryRequest):
    require_csrf(request, body.csrf_token)
    target = (f"{body.schema_name}.integration_outbox", "event_id") if body.operation == "reset_outbox" else (("healthmind.ai_task_attempts", "attempt_id") if body.operation == "recover_attempt" else ("healthmind.ai_tasks", "task_id"))
    snapshot = await request.app.state.repo.snapshot(*target, body.record_id)
    if not snapshot: raise HTTPException(404, "record not found")
    token, preview = request.app.state.previews.create("recovery."+body.operation, body.model_dump(exclude={"preview_token"}), snapshot)
    return {"preview_token": token, "expires_at": preview.expires_at, "snapshot": serial(redact(snapshot)), "confirmation": f"RECOVER {body.record_id}"}


@app.post("/api/recovery/execute")
async def recovery_execute(request: Request, body: RecoveryRequest):
    require_csrf(request, body.csrf_token); request.app.state.previews.consume(body.preview_token or "", "recovery."+body.operation)
    if body.confirmation != f"RECOVER {body.record_id}": raise HTTPException(409, "confirmation text mismatch")
    op = request.app.state.audit.write("recovery."+body.operation, body.record_id, body.reason, "started")
    try:
        result = await request.app.state.repo.recover(body.operation, body.schema_name, body.record_id)
        request.app.state.audit.write("recovery."+body.operation, body.record_id, body.reason, "succeeded", operation_id=op, result=result)
        return serial(result)
    except Exception as exc:
        request.app.state.audit.write("recovery."+body.operation, body.record_id, body.reason, "failed", operation_id=op, error=str(exc)); raise


@app.get("/api/events")
async def events(request: Request):
    async def stream():
        while True:
            if await request.is_disconnected(): break
            try: payload = await request.app.state.repo.status()
            except Exception as exc: payload = {"error": str(exc)}
            yield f"event: status\ndata: {json.dumps(serial(payload), ensure_ascii=False)}\n\n"
            await asyncio.sleep(settings.refresh_seconds)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

