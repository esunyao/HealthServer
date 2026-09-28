from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
import psycopg

from nutriathena_agent.database import ConflictError, Repository
from nutriathena_agent.migrations import MigrationError, apply_migrations
from nutriathena_agent.runtime_config import RuntimeSettings
from nutriathena_agent.worker import DurableWorker

pytestmark = pytest.mark.integration
_TASK = UUID("11111111-1111-4111-8111-111111111111")
_RELEASE = UUID("33333333-3333-4333-8333-333333333333")
_ACTUAL_DIGEST = "a" * 64


@pytest.fixture(scope="module")
def postgres_database():
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker is required for the isolated PostgreSQL runtime test")
    info = subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True)
    if info.returncode != 0:
        pytest.skip("Docker engine is unavailable")

    context_name = subprocess.run(
        [docker, "context", "show"], capture_output=True, text=True, check=True, timeout=10
    ).stdout.strip()
    context_json = subprocess.run(
        [docker, "context", "inspect", context_name], capture_output=True, text=True, check=True, timeout=10
    ).stdout
    docker_host = json.loads(context_json)[0]["Endpoints"]["docker"]["Host"]
    remote_ssh = docker_host.startswith("ssh://")
    name = f"nutriathena-agent-test-{uuid4().hex[:12]}"
    if remote_ssh:
        remote_port = 40000 + (uuid4().int % 20000)
        docker_args = [
            docker, "run", "--detach", "--rm", "--name", name, "--network", "host",
            "--env", "POSTGRES_PASSWORD=unit-test-only",
            "--env", "POSTGRES_DB=agent_test",
            "--env", f"PGPORT={remote_port}",
            "postgres:17-alpine", "-c", "listen_addresses=127.0.0.1",
        ]
    elif docker_host.startswith("npipe://"):
        docker_args = [
            docker, "run", "--detach", "--rm", "--name", name,
            "--env", "POSTGRES_PASSWORD=unit-test-only",
            "--env", "POSTGRES_DB=agent_test",
            "--publish", "127.0.0.1::5432",
            "postgres:17-alpine",
        ]
    else:
        pytest.skip("The active Docker context has no supported local/SSH endpoint")
    created = subprocess.run(docker_args, capture_output=True, text=True, timeout=120)
    if created.returncode != 0:
        pytest.skip("Could not start the ephemeral PostgreSQL test container")
    container_id = created.stdout.strip()
    tunnel = None
    try:
        if remote_ssh:
            ssh_binary = shutil.which("ssh")
            parsed_host = urlsplit(docker_host)
            if ssh_binary is None or not parsed_host.hostname or not parsed_host.username:
                pytest.skip("SSH is needed to tunnel to the configured remote Docker context")
            with socket.socket() as socket_probe:
                socket_probe.bind(("127.0.0.1", 0))
                local_port = socket_probe.getsockname()[1]
            tunnel = subprocess.Popen(
                [
                    ssh_binary,
                    "-o", "BatchMode=yes",
                    "-o", "ExitOnForwardFailure=yes",
                    "-N",
                    "-L", f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}",
                    f"{parsed_host.username}@{parsed_host.hostname}",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            port_result = subprocess.run(
                [docker, "port", container_id, "5432/tcp"], capture_output=True, text=True, check=True, timeout=10
            )
            local_port = int(port_result.stdout.strip().rsplit(":", 1)[1])
        database_url = f"postgresql://postgres:unit-test-only@127.0.0.1:{local_port}/agent_test"
        deadline = time.monotonic() + (8 if remote_ssh else 60)
        while True:
            try:
                if tunnel is not None and tunnel.poll() is not None:
                    pytest.fail("SSH tunnel to the isolated PostgreSQL container exited")
                with psycopg.connect(database_url, connect_timeout=2):
                    break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    if remote_ssh:
                        pytest.skip("The remote Docker host does not expose its isolated loopback database through SSH")
                    pytest.fail("Ephemeral PostgreSQL did not become ready")
                time.sleep(0.5)
        yield database_url
    finally:
        if tunnel is not None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill()
        subprocess.run([docker, "stop", container_id], capture_output=True, text=True, timeout=30)


def _payload(attempt_id: UUID, trace_id: str = "trace-test") -> dict[str, object]:
    return {
        "assistant_id": "assistant-test",
        "input": {"task_id": str(_TASK), "attempt_id": str(attempt_id), "trace_id": trace_id},
        "metadata": {
            "task_id": str(_TASK),
            "attempt_id": str(attempt_id),
            "release_id": str(_RELEASE),
            "artifact_sha256": _ACTUAL_DIGEST,
        },
        "on_completion": "keep",
    }


def _request_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class FakeMealRunner:
    async def run(self, *, task_id: str, attempt_id: str, trace_id: str):
        assert task_id == str(_TASK)
        assert trace_id == "trace-test"
        return {
            "overall_confidence": 0.8,
            "items": [
                {
                    "name": "米饭",
                    "weight_grams": 100,
                    "confidence": 0.8,
                    "nutrients": [{"code": "ENERGY_KCAL", "value": 116}],
                }
            ],
        }


def test_migration_idempotency_fencing_cancel_retention_and_worker(postgres_database, tmp_path):
    repository = Repository(postgres_database)
    repository.open()
    try:
        applied = apply_migrations(repository.pool)
        assert applied == ["0001_create_agent_runtime.sql"]
        assert apply_migrations(repository.pool) == []
        repository.assert_schema_ready()

        with repository.pool.connection() as connection:
            names = connection.execute(
                """SELECT table_name FROM information_schema.tables
                   WHERE table_schema = 'nutriathena_agent' ORDER BY table_name"""
            ).fetchall()
        assert {row[0] for row in names} == {"schema_migrations", "agent_runs", "agent_threads"}

        changed_dir = tmp_path / "changed-migration"
        changed_dir.mkdir()
        original = Path(__file__).resolve().parents[1] / "migrations" / "0001_create_agent_runtime.sql"
        (changed_dir / original.name).write_bytes(original.read_bytes() + b"\n-- changed checksum\n")
        with pytest.raises(MigrationError, match="校验和发生变化"):
            apply_migrations(repository.pool, changed_dir)

        attempt_success = UUID("22222222-2222-4222-8222-222222222222")
        repository.create_thread(attempt_success, _TASK, attempt_success)
        payload = _payload(attempt_success)
        run, created = repository.submit_run(
            thread_id=attempt_success,
            task_id=_TASK,
            attempt_id=attempt_success,
            release_id=_RELEASE,
            request_payload=payload,
            request_sha256=_request_hash(payload),
            requested_assistant_id="assistant-test",
            requested_artifact_sha256=_ACTUAL_DIGEST,
            deployment_key="deployment-test",
            assistant_id="assistant-test",
            artifact_sha256=_ACTUAL_DIGEST,
        )
        duplicate, duplicate_created = repository.submit_run(
            thread_id=attempt_success,
            task_id=_TASK,
            attempt_id=attempt_success,
            release_id=_RELEASE,
            request_payload=payload,
            request_sha256=_request_hash(payload),
            requested_assistant_id="assistant-test",
            requested_artifact_sha256=_ACTUAL_DIGEST,
            deployment_key="deployment-test",
            assistant_id="assistant-test",
            artifact_sha256=_ACTUAL_DIGEST,
        )
        assert created and not duplicate_created
        assert duplicate["run_id"] == run["run_id"]
        changed_payload = _payload(attempt_success, "different-trace")
        with pytest.raises(ConflictError, match="IDEMPOTENCY_CONFLICT"):
            repository.submit_run(
                thread_id=attempt_success,
                task_id=_TASK,
                attempt_id=attempt_success,
                release_id=_RELEASE,
                request_payload=changed_payload,
                request_sha256=_request_hash(changed_payload),
                requested_assistant_id="assistant-test",
                requested_artifact_sha256=_ACTUAL_DIGEST,
                deployment_key="deployment-test",
                assistant_id="assistant-test",
                artifact_sha256=_ACTUAL_DIGEST,
            )

        settings = RuntimeSettings(
            host="127.0.0.1", port=8101, database_url="unused",
            oauth_issuer="https://issuer.test", oauth_jwks_url="https://issuer.test/jwks",
            oauth_audience="aud", oauth_client_id="client", oauth_scope="scope",
            release_id=_RELEASE, deployment_key="deployment-test", assistant_id="assistant-test",
            worker_poll_seconds=0.1, lease_seconds=10, run_timeout_seconds=20,
        )
        worker = DurableWorker(repository, settings, runner=FakeMealRunner())
        assert asyncio.run(worker.run_once())
        succeeded = repository.get_run(run["run_id"])
        assert succeeded["status"] == "success"
        assert succeeded["result_payload"]["items"][0]["name"] == "米饭"
        assert succeeded["result_expires_at"] >= succeeded["completed_at"]
        assert succeeded["retention_until"] >= succeeded["completed_at"]

        with repository.pool.connection() as connection:
            connection.execute(
                "UPDATE nutriathena_agent.agent_runs SET result_expires_at = now() - interval '1 second' WHERE run_id = %s",
                (run["run_id"],),
            )
        assert repository.purge_expired_results() == 1
        purged = repository.get_run(run["run_id"])
        assert purged["status"] == "success"
        assert purged["result_payload"] is None and purged["result_sha256"] is None
        assert purged["result_purged_at"] is not None

        attempt_stale = UUID("22222222-2222-4222-8222-222222222223")
        repository.create_thread(attempt_stale, _TASK, attempt_stale)
        stale_payload = _payload(attempt_stale)
        stale_run, _ = repository.submit_run(
            thread_id=attempt_stale, task_id=_TASK, attempt_id=attempt_stale, release_id=_RELEASE,
            request_payload=stale_payload, request_sha256=_request_hash(stale_payload),
            requested_assistant_id="assistant-test", requested_artifact_sha256=_ACTUAL_DIGEST,
            deployment_key="deployment-test", assistant_id="assistant-test", artifact_sha256=_ACTUAL_DIGEST,
        )
        claimed = repository.claim_pending("old-worker", 10)
        assert claimed and claimed["run_id"] == stale_run["run_id"]
        with repository.pool.connection() as connection:
            connection.execute(
                "UPDATE nutriathena_agent.agent_runs SET lease_expires_at = now() - interval '1 second' WHERE run_id = %s",
                (stale_run["run_id"],),
            )
        assert repository.interrupt_expired_leases() == 1
        assert not repository.finish_success(
            stale_run["run_id"], "old-worker", claimed["lease_version"], {"status": "bad"}, "b" * 64
        )
        assert repository.get_run(stale_run["run_id"])["status"] == "interrupted"

        attempt_cancel = UUID("22222222-2222-4222-8222-222222222224")
        repository.create_thread(attempt_cancel, _TASK, attempt_cancel)
        cancel_payload = _payload(attempt_cancel)
        cancel_run, _ = repository.submit_run(
            thread_id=attempt_cancel, task_id=_TASK, attempt_id=attempt_cancel, release_id=_RELEASE,
            request_payload=cancel_payload, request_sha256=_request_hash(cancel_payload),
            requested_assistant_id="assistant-test", requested_artifact_sha256=_ACTUAL_DIGEST,
            deployment_key="deployment-test", assistant_id="assistant-test", artifact_sha256=_ACTUAL_DIGEST,
        )
        cancelled = repository.request_cancel(cancel_run["run_id"])
        assert cancelled["status"] == "interrupted" and cancelled["error_code"] == "CANCELLED"
        assert cancelled["retention_until"] is not None
        repeated_cancel = repository.request_cancel(cancel_run["run_id"])
        assert repeated_cancel["completed_at"] == cancelled["completed_at"]

        attempt_cancel_running = UUID("22222222-2222-4222-8222-222222222225")
        repository.create_thread(attempt_cancel_running, _TASK, attempt_cancel_running)
        running_payload = _payload(attempt_cancel_running)
        running_cancel_run, _ = repository.submit_run(
            thread_id=attempt_cancel_running, task_id=_TASK, attempt_id=attempt_cancel_running,
            release_id=_RELEASE, request_payload=running_payload,
            request_sha256=_request_hash(running_payload),
            requested_assistant_id="assistant-test", requested_artifact_sha256=_ACTUAL_DIGEST,
            deployment_key="deployment-test", assistant_id="assistant-test", artifact_sha256=_ACTUAL_DIGEST,
        )
        running_claim = repository.claim_pending("cancelled-worker", 10)
        assert running_claim and running_claim["run_id"] == running_cancel_run["run_id"]
        requested = repository.request_cancel(running_cancel_run["run_id"])
        assert requested["status"] == "running" and requested["cancel_requested_at"] is not None
        assert not repository.finish_success(
            running_cancel_run["run_id"], "cancelled-worker", running_claim["lease_version"],
            {"overall_confidence": 0.8, "items": []}, "c" * 64,
        )
        after_finish = repository.get_run(running_cancel_run["run_id"])
        assert after_finish["status"] == "interrupted"
        assert after_finish["error_code"] == "CANCELLED"

        with repository.pool.connection() as connection:
            connection.execute(
                "UPDATE nutriathena_agent.agent_runs SET retention_until = now() - interval '1 second'"
            )
            connection.execute(
                "UPDATE nutriathena_agent.agent_threads SET created_at = now() - interval '181 days'"
            )
        assert repository.purge_expired_rows() == (4, 4)

    finally:
        repository.close()
