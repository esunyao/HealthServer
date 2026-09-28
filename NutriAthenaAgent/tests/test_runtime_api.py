from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from nutriathena_agent.api import create_app
from nutriathena_agent.database import ConflictError
from nutriathena_agent.runtime_config import RuntimeSettings

TASK_ID = UUID("11111111-1111-4111-8111-111111111111")
ATTEMPT_ID = UUID("22222222-2222-4222-8222-222222222222")
RELEASE_ID = UUID("33333333-3333-4333-8333-333333333333")
ARTIFACT_SHA = "a" * 64


def _settings() -> RuntimeSettings:
    return RuntimeSettings(
        host="127.0.0.1",
        port=8101,
        database_url="postgresql://unused",
        oauth_issuer="https://issuer.example.test",
        oauth_jwks_url="https://issuer.example.test/jwks",
        oauth_audience="healthmind-agent",
        oauth_client_id="healthmind",
        oauth_scope="healthmind.agent.run",
        release_id=RELEASE_ID,
        deployment_key="deployment-meal-v1",
        assistant_id="meal-assistant-v1",
    )


class FakeTokenVerifier:
    async def verify(self, token: str):
        if token != "signed-test-token":
            raise HTTPException(status_code=401, detail="Invalid service access token")
        return {"sub": "healthmind"}


class FakeRepository:
    def __init__(self):
        self.threads = {}
        self.runs_by_id = {}
        self.runs_by_attempt = {}

    def health_check(self):
        return True

    def create_thread(self, thread_id, task_id, attempt_id):
        if thread_id != attempt_id:
            raise ConflictError("thread identity conflict")
        existing = self.threads.get(attempt_id)
        if existing and existing["task_id"] != task_id:
            raise ConflictError("thread identity conflict")
        row = {"thread_id": thread_id, "task_id": task_id, "attempt_id": attempt_id}
        self.threads[attempt_id] = row
        return row

    def get_thread(self, thread_id):
        return self.threads.get(thread_id)

    def submit_run(self, **kwargs):
        attempt_id = kwargs["attempt_id"]
        existing = self.runs_by_attempt.get(attempt_id)
        if existing:
            if existing["request_sha256"] != kwargs["request_sha256"]:
                raise ConflictError("IDEMPOTENCY_CONFLICT")
            return existing, False
        run_id = uuid4()
        now = datetime.now(timezone.utc)
        row = {
            "run_id": run_id,
            "thread_id": kwargs["thread_id"],
            "task_id": kwargs["task_id"],
            "attempt_id": attempt_id,
            "release_id": kwargs["release_id"],
            "request_payload": kwargs["request_payload"],
            "request_sha256": kwargs["request_sha256"],
            "agent_deployment_key": kwargs["deployment_key"],
            "agent_assistant_id": kwargs["assistant_id"],
            "agent_artifact_sha256": kwargs["artifact_sha256"],
            "status": "pending",
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "error_code": None,
            "error_message": None,
        }
        self.runs_by_id[run_id] = row
        self.runs_by_attempt[attempt_id] = row
        return row, True

    def list_runs(self, thread_id):
        return [row for row in self.runs_by_id.values() if row["thread_id"] == thread_id]

    def get_run(self, run_id):
        return self.runs_by_id.get(run_id)

    def request_cancel(self, run_id):
        return self.runs_by_id.get(run_id)


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer signed-test-token"}


def _run_body() -> dict[str, object]:
    return {
        "assistant_id": "meal-assistant-v1",
        "input": {
            "task_id": str(TASK_ID),
            "attempt_id": str(ATTEMPT_ID),
            "trace_id": "trace-for-test",
        },
        "metadata": {
            "task_id": str(TASK_ID),
            "attempt_id": str(ATTEMPT_ID),
            "release_id": str(RELEASE_ID),
            "artifact_sha256": ARTIFACT_SHA,
        },
        "on_completion": "keep",
    }


def _client(repository: FakeRepository) -> TestClient:
    app = create_app(
        settings=_settings(),
        repository=repository,
        token_verifier=FakeTokenVerifier(),
        start_worker=False,
        artifact_sha256=ARTIFACT_SHA,
    )
    return TestClient(app)


def test_healthmind_http_contract_persists_and_reuses_one_run():
    repository = FakeRepository()
    with _client(repository) as client:
        thread = client.post(
            "/threads",
            headers=_headers(),
            json={"thread_id": str(ATTEMPT_ID), "metadata": {"task_id": str(TASK_ID)}},
        )
        assert thread.status_code == 200
        assert thread.json() == {"thread_id": str(ATTEMPT_ID)}

        url = f"/threads/{ATTEMPT_ID}/runs"
        headers = {**_headers(), "Idempotency-Key": str(ATTEMPT_ID)}
        first = client.post(url, headers=headers, json=_run_body())
        second = client.post(url, headers=headers, json=_run_body())
        assert first.status_code == second.status_code == 200
        assert first.json()["run_id"] == second.json()["run_id"]
        assert first.json()["status"] == "pending"
        assert first.json()["assistant_id"] == "meal-assistant-v1"
        assert first.json()["metadata"]["release_id"] == str(RELEASE_ID)
        assert first.json()["metadata"]["artifact_sha256"] == ARTIFACT_SHA

        run_id = first.json()["run_id"]
        assert client.get(f"/runs/{run_id}", headers=_headers()).json()["status"] == "pending"
        assert client.get(f"/threads/{ATTEMPT_ID}/runs", headers=_headers()).json() == [first.json()]

        changed = _run_body()
        changed["input"]["trace_id"] = "different-request"
        conflict = client.post(url, headers=headers, json=changed)
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
        assert len(repository.runs_by_id) == 1


def test_api_rejects_missing_or_invalid_service_token_and_release_mismatch():
    repository = FakeRepository()
    with _client(repository) as client:
        no_token = client.post(
            "/threads",
            json={"thread_id": str(ATTEMPT_ID), "metadata": {"task_id": str(TASK_ID)}},
        )
        assert no_token.status_code == 401
        bad_token = client.post(
            "/threads",
            headers={"Authorization": "Bearer wrong"},
            json={"thread_id": str(ATTEMPT_ID), "metadata": {"task_id": str(TASK_ID)}},
        )
        assert bad_token.status_code == 401

        client.post(
            "/threads",
            headers=_headers(),
            json={"thread_id": str(ATTEMPT_ID), "metadata": {"task_id": str(TASK_ID)}},
        )
        body = _run_body()
        body["metadata"]["release_id"] = str(UUID("44444444-4444-4444-8444-444444444444"))
        response = client.post(
            f"/threads/{ATTEMPT_ID}/runs",
            headers={**_headers(), "Idempotency-Key": str(ATTEMPT_ID)},
            json=body,
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "RELEASE_ID_MISMATCH"
