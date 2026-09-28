from __future__ import annotations

import asyncio
from uuid import uuid4

from nutriathena_agent.runtime_config import RuntimeSettings
from nutriathena_agent.worker import DurableWorker


def _settings(**overrides) -> RuntimeSettings:
    values = dict(
        host="127.0.0.1", port=8101, database_url="unused",
        oauth_issuer="https://issuer.test", oauth_jwks_url="https://issuer.test/jwks",
        oauth_audience="aud", oauth_client_id="client", oauth_scope="scope",
        release_id=uuid4(), deployment_key="deployment-test", assistant_id="assistant-test",
        worker_poll_seconds=0.1, lease_seconds=3, run_timeout_seconds=5,
    )
    values.update(overrides)
    return RuntimeSettings(**values)


def _pending_row() -> dict[str, object]:
    return {
        "run_id": uuid4(),
        "task_id": uuid4(),
        "attempt_id": uuid4(),
        "lease_version": 1,
        "request_payload": {"input": {"trace_id": "trace-test"}},
    }


class FakeRepository:
    def __init__(self, row: dict[str, object], *, renew_result=(True, False)):
        self.row = row
        self.renew_result = renew_result
        self.finished_success = []
        self.finished_terminal = []
        self.claimed = False

    def interrupt_expired_leases(self):
        return 0

    def purge_expired_results(self):
        return 0

    def purge_expired_rows(self):
        return 0, 0

    def claim_pending(self, owner, lease_seconds):
        if self.claimed:
            return None
        self.claimed = True
        self.row["lease_owner"] = owner
        return self.row

    def renew_lease(self, run_id, owner, version, lease_seconds):
        return self.renew_result

    def finish_success(self, *args):
        self.finished_success.append(args)
        return True

    def finish_terminal(self, run_id, owner, version, **kwargs):
        self.finished_terminal.append((run_id, owner, version, kwargs))
        return True


class SuccessfulRunner:
    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = False

    async def run(self, *, task_id, attempt_id, trace_id):
        self.started.set()
        return {
            "overall_confidence": 0.9,
            "items": [
                {
                    "name": "苹果",
                    "weight_grams": 120,
                    "confidence": 0.9,
                    "nutrients": [{"code": "ENERGY_KCAL", "value": 62}],
                }
            ],
        }


class BlockingRunner:
    def __init__(self):
        self.started = asyncio.Event()
        self.was_cancelled = False

    async def run(self, *, task_id, attempt_id, trace_id):
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise


def test_worker_validates_contract_and_commits_only_through_current_lease():
    row = _pending_row()
    repository = FakeRepository(row)
    runner = SuccessfulRunner()
    worker = DurableWorker(repository, _settings(lease_seconds=10), runner=runner)
    assert asyncio.run(worker.run_once())
    assert len(repository.finished_success) == 1
    result = repository.finished_success[0][-2]
    assert result["items"][0]["name"] == "苹果"
    assert repository.finished_terminal == []


def test_worker_stops_model_call_if_lease_is_lost():
    async def scenario():
        row = _pending_row()
        repository = FakeRepository(row, renew_result=(False, False))
        runner = BlockingRunner()
        worker = DurableWorker(repository, _settings(lease_seconds=3), runner=runner)
        run_once = asyncio.create_task(worker.run_once())
        await asyncio.wait_for(runner.started.wait(), timeout=1)
        await asyncio.wait_for(run_once, timeout=2)
        assert runner.was_cancelled
        assert repository.finished_success == []
        assert repository.finished_terminal == []

    asyncio.run(scenario())


def test_worker_cancels_model_call_without_claiming_timeout_when_heartbeat_fails():
    class UnavailableRepository(FakeRepository):
        def renew_lease(self, run_id, owner, version, lease_seconds):
            raise RuntimeError("private database connection detail")

    async def scenario():
        row = _pending_row()
        repository = UnavailableRepository(row)
        runner = BlockingRunner()
        worker = DurableWorker(repository, _settings(lease_seconds=3), runner=runner)
        run_once = asyncio.create_task(worker.run_once())
        await asyncio.wait_for(runner.started.wait(), timeout=1)
        await asyncio.wait_for(run_once, timeout=2)
        assert runner.was_cancelled
        assert repository.finished_success == []
        assert repository.finished_terminal == []

    asyncio.run(scenario())


def test_worker_honors_cancel_request_and_timeout_without_leaking_exception_text():
    async def cancellation_scenario():
        row = _pending_row()
        repository = FakeRepository(row, renew_result=(True, True))
        runner = BlockingRunner()
        worker = DurableWorker(repository, _settings(lease_seconds=3), runner=runner)
        await worker.run_once()
        assert runner.was_cancelled
        assert repository.finished_terminal[0][-1]["status"] == "interrupted"
        assert repository.finished_terminal[0][-1]["error_code"] == "CANCELLED"

    asyncio.run(cancellation_scenario())

    async def timeout_scenario():
        row = _pending_row()
        repository = FakeRepository(row, renew_result=(True, False))
        runner = BlockingRunner()
        worker = DurableWorker(repository, _settings(run_timeout_seconds=0.05, lease_seconds=10), runner=runner)
        await worker._execute({**row, "lease_owner": worker.owner})
        assert runner.was_cancelled
        assert repository.finished_terminal[0][-1]["status"] == "error"
        assert repository.finished_terminal[0][-1]["error_code"] == "AGENT_RUN_TIMEOUT"

    asyncio.run(timeout_scenario())
