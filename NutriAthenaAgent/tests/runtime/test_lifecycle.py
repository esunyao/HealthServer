import asyncio

import pytest
from fastapi.testclient import TestClient

from nutriathena_agent.api import create_app
from nutriathena_agent.runtime import bootstrap
from tests.contract.test_runtime_api import ARTIFACT_SHA, FakeRepository, FakeTokenVerifier, _settings


@pytest.mark.parametrize("stage", ["open", "schema"])
def test_owned_pool_is_closed_when_startup_fails(monkeypatch, stage):
    calls = []

    class Pool:
        def open(self):
            calls.append("open")
            if stage == "open":
                raise RuntimeError("test startup failure")

        def assert_schema_ready(self):
            calls.append("schema")
            raise RuntimeError("test schema failure")

        def close(self):
            calls.append("close")

    monkeypatch.setattr(bootstrap, "Repository", lambda *args, **kwargs: Pool())
    app = create_app(settings=_settings(), token_verifier=FakeTokenVerifier(),
                     start_worker=False, artifact_sha256=ARTIFACT_SHA)
    with pytest.raises(RuntimeError, match="test .* failure"):
        with TestClient(app):
            pass
    assert calls == (["open", "close"] if stage == "open" else ["open", "schema", "close"])


def test_injected_repository_lifetime_stays_with_its_caller():
    class ExternalRepository(FakeRepository):
        def open(self):
            pytest.fail("application opened an externally owned repository")

        def close(self):
            pytest.fail("application closed an externally owned repository")

    repository = ExternalRepository()
    app = create_app(settings=_settings(), repository=repository, token_verifier=FakeTokenVerifier(),
                     start_worker=False, artifact_sha256=ARTIFACT_SHA)
    for _ in range(2):
        with TestClient(app) as client:
            assert client.get("/healthz").json() == {"status": "ok"}


def test_worker_task_is_cancelled_and_joined_on_shutdown(monkeypatch):
    events = []

    class Worker:
        def __init__(self, *args, **kwargs):
            pass

        async def run_forever(self):
            events.append("started")
            try:
                await asyncio.Event().wait()
            finally:
                events.append("joined")

        async def stop(self):
            events.append("stopped")

    monkeypatch.setattr(bootstrap, "DurableWorker", Worker)
    app = create_app(settings=_settings(), repository=FakeRepository(), token_verifier=FakeTokenVerifier(),
                     start_worker=True, artifact_sha256=ARTIFACT_SHA)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
    assert events == ["started", "stopped", "joined"]
