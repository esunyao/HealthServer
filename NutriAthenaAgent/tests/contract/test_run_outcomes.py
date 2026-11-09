import pytest

from tests.contract.test_runtime_api import (
    ATTEMPT_ID, RUN_ID, FakeRepository, _client, _headers, _run_body, _thread_body,
)


@pytest.mark.parametrize("state,payload,error_code,expected,detail", [
    ("success", {"items": []}, None, 200, {"output": {"items": []}}),
    ("success", None, None, 410, {"detail": {"code": "RESULT_EXPIRED"}}),
    ("error", None, "MODEL_FAILED", 409, {"detail": {"code": "MODEL_FAILED", "status": "error"}}),
    ("interrupted", None, "CANCELLED", 409, {"detail": {"code": "CANCELLED", "status": "interrupted"}}),
])
def test_wait_outcomes_preserve_http_contract(state, payload, error_code, expected, detail):
    repository = FakeRepository()
    with _client(repository) as client:
        client.post("/threads", headers=_headers(), json=_thread_body())
        client.post(f"/threads/{ATTEMPT_ID}/runs", json=_run_body(),
                    headers={**_headers(), "Idempotency-Key": str(ATTEMPT_ID)})
        row = repository.runs_by_id[RUN_ID]
        row.update(status=state, result_payload=payload, error_code=error_code)
        response = client.get(f"/runs/{RUN_ID}/wait?timeout_seconds=1", headers=_headers())
    assert response.status_code == expected
    assert response.json() == detail


def test_health_probe_recovers_after_a_database_failure():
    class RecoveringRepository(FakeRepository):
        attempts = 0

        def health_check(self):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("isolated database outage")
            return True

    with _client(RecoveringRepository()) as client:
        assert client.get("/healthz").status_code == 503
        assert client.get("/healthz").json() == {"status": "ok"}
