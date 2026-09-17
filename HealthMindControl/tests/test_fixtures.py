from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from healthmind_control.api.fixtures import router
from healthmind_control.repositories.fixtures import HOLD_UNTIL, FIXTURE_TABLES, FixturesMixin, resolve_fixture_mappings
from healthmind_control.security import PreviewStore


def test_fixture_mapping_resolves_inherit_generators_and_hash():
    values = resolve_fixture_mappings({
        "task_id": {"mode": "generate", "generator": "uuid"},
        "trace_id": {"mode": "inherit", "source_field": "flat.trace_id"},
        "payload": {"mode": "manual", "value": {"meal_id": "2097632617381867522"}},
        "payload_sha256": {"mode": "generate", "generator": "sha256", "source_field": "$payload"},
        "next_attempt_at": {"mode": "generate", "generator": "hold_until"},
    }, {"flat": {"trace_id": "trace-1"}}, datetime(2026, 9, 15, tzinfo=UTC))
    assert values["trace_id"] == "trace-1"
    assert len(values["task_id"]) == 36
    assert len(values["payload_sha256"]) == 64
    assert values["next_attempt_at"] == HOLD_UNTIL


def test_fixture_whitelist_contains_runtime_tables_not_release_configuration():
    assert "healthmind.ai_tasks" in FIXTURE_TABLES
    assert "healthmind.integration_outbox" in FIXTURE_TABLES
    assert "nutri.meal_records" in FIXTURE_TABLES
    assert "healthmind.workflow_releases" not in FIXTURE_TABLES
    assert "healthmind.ai_tool_definitions" not in FIXTURE_TABLES


def test_mcp_execute_uses_ids_frozen_by_preview():
    class FakeRepo:
        created = None
        create_count = 0

        async def fixture_source_snapshot(self, task_id):
            return {"task_id": task_id, "status": "failed", "lock_version": 1}

        async def prepare_mcp_session(self, source_task_id, inherit_trace_id, lease_minutes):
            return {
                "task_id": "11111111-1111-4111-8111-111111111111",
                "attempt_id": "22222222-2222-4222-8222-222222222222",
                "trace_id": "trace-source", "session_id": "session-1",
                "lease_until": "2026-09-15T10:50:00+00:00", "source_task_id": source_task_id,
                "manifest": {"hmc_mcp_session": True}, "bindings": [{"tool_code": "tool"}],
            }

        async def create_mcp_session(self, intent):
            self.create_count += 1
            self.created = dict(intent)
            return {key: intent[key] for key in ("task_id", "attempt_id", "trace_id", "session_id", "lease_until")}

    class FakeAudit:
        def write(self, *args, **kwargs):
            return kwargs.get("operation_id", "op-1")

    class FakeStore:
        def create(self, name, mode, context):
            return {"run_id": "run-1"}

        def record(self, *args):
            return "record-1"

    repo = FakeRepo()
    app = FastAPI()
    app.include_router(router)
    app.state.csrf_token = "csrf"
    app.state.previews = PreviewStore(120)
    app.state.repo = repo
    app.state.db = SimpleNamespace(write_features={"fixtures": True}, schema_error=None)
    app.state.settings = SimpleNamespace(fixture_mcp_lease_minutes=50)
    app.state.audit = FakeAudit()
    app.state.debug_store = FakeStore()
    with TestClient(app) as client:
        preview = client.post("/api/fixtures/mcp-session/preview", json={
            "csrf_token": "csrf", "reason": "manual MCP test",
            "source_task_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        }).json()
        bad = client.post("/api/fixtures/mcp-session/execute", json={
            "csrf_token": "csrf", "preview_token": preview["preview_token"],
            "confirmation": "WRONG",
        })
        response = client.post("/api/fixtures/mcp-session/execute", json={
            "csrf_token": "csrf", "preview_token": preview["preview_token"],
            "confirmation": "MCP TEST aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            # ExecuteRequest 不接受也不读取这些伪造字段。
            "task_id": "attacker", "attempt_id": "attacker",
        })
        replay = client.post("/api/fixtures/mcp-session/execute", json={
            "csrf_token": "csrf", "preview_token": preview["preview_token"],
            "confirmation": "MCP TEST aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        })
    assert bad.status_code == 409
    assert bad.json()["detail"]["code"] == "CONFIRMATION_MISMATCH"
    assert response.status_code == 200
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert repo.create_count == 1
    assert repo.created["task_id"] == "11111111-1111-4111-8111-111111111111"
    assert repo.created["attempt_id"] == "22222222-2222-4222-8222-222222222222"


def test_mcp_preview_rejects_bad_csrf():
    app = FastAPI()
    app.include_router(router)
    app.state.csrf_token = "csrf"
    with TestClient(app) as client:
        response = client.post("/api/fixtures/mcp-session/preview", json={
            "csrf_token": "wrong", "reason": "manual test",
            "source_task_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        })
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_mcp_close_qualifies_attempt_started_at_and_updates_both_rows():
    class Cursor:
        def __init__(self, row):
            self.row = row

        async def fetchone(self):
            return self.row

    class Connection:
        def __init__(self):
            self.sql = []

        async def execute(self, statement, params):
            text = str(statement)
            self.sql.append(text)
            if "ai_task_attempts" in text:
                return Cursor({"attempt_id": "attempt-1"})
            return Cursor({"task_id": "task-1", "status": "cancelled", "trace_id": "trace-1"})

    class Db:
        def __init__(self):
            self.conn = Connection()

        @asynccontextmanager
        async def transaction(self):
            yield self.conn

    repo = FixturesMixin()
    repo.db = Db()
    result = await repo.close_mcp_session("task-1")
    assert result["attempt_id"] == "attempt-1"
    assert "now()-a.started_at" in repo.db.conn.sql[0]
    assert "status='cancelled'" in repo.db.conn.sql[0]
    assert "completed_at=now()" in repo.db.conn.sql[1]
import pytest
