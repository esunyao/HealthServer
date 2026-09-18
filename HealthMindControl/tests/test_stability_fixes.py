import asyncio
import json
import os
import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from healthmind_control.api.debug import router as debug_router
from healthmind_control.api.kafka import router as kafka_router
from healthmind_control.api.releases import router as releases_router
from healthmind_control.audit import AuditLog
from healthmind_control.security import PreviewStore
from healthmind_control.services.kafka import KafkaService


def test_kafka_headers_are_json_safe_and_preserve_repeated_keys():
    headers = KafkaService._headers_json_safe([
        ("trace", b"text"), ("trace", b"\xff\x00"), ("empty", None),
    ])
    assert headers == [
        {"key": "trace", "value": "text", "encoding": "utf-8"},
        {"key": "trace", "value": "/wA=", "encoding": "base64"},
        {"key": "empty", "value": None, "encoding": "null"},
    ]
    json.dumps(headers)


def test_release_bind_preview_cannot_execute_as_release_mutation():
    app = FastAPI()
    app.include_router(releases_router)
    app.state.csrf_token = "csrf"
    app.state.previews = PreviewStore(120)
    token, _ = app.state.previews.create("release.bind_tools", {"release_id": "x"}, {"release_id": "x"})
    with TestClient(app) as client:
        response = client.post("/api/releases/execute", json={
            "csrf_token": "csrf", "preview_token": token, "confirmation": "RELEASE CREATE",
        })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PREVIEW_TARGET_MISMATCH"


def test_invalid_pagination_is_rejected_before_backends_are_accessed():
    debug_app = FastAPI()
    debug_app.include_router(debug_router)
    with TestClient(debug_app) as client:
        assert client.get("/api/debug/runs?limit=-1").status_code == 422
        assert client.get("/api/debug/runs?limit=abc").status_code == 422

    kafka_app = FastAPI()
    kafka_app.include_router(kafka_router)
    with TestClient(kafka_app) as client:
        assert client.get("/api/kafka/messages?topic=x&partition=-1").status_code == 422
        assert client.get("/api/kafka/messages?topic=x&offset=-1").status_code == 422


def test_audit_rotation_retention_and_reverse_tail(tmp_path):
    path = tmp_path / "admin-actions.jsonl"
    audit = AuditLog(path, rotate_bytes=1, retention_days=90)

    async def write_entries():
        await audit.write("first", "one", "test", "succeeded")
        await audit.write("second", "two", "test", "succeeded")
        return await audit.tail(10)

    entries = asyncio.run(write_entries())
    assert [entry["action"] for entry in entries] == ["second", "first"]
    archive = next(tmp_path.glob("admin-actions.*.jsonl"))
    old = time.time() - 91 * 86400
    os.utime(archive, (old, old))
    asyncio.run(audit.write("third", "three", "test", "succeeded"))
    assert not archive.exists()
    assert path.exists()
