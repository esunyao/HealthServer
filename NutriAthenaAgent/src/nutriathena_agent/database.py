"""PostgreSQL persistence for thread identity, runs, leases, and retention."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .migrations import SCHEMA


class ConflictError(RuntimeError):
    """A requested identity is already bound to different content."""


class Repository:
    def __init__(
        self,
        database_url: str,
        *,
        row_retention_days: int = 180,
        result_retention_hours: int = 24,
        pool: Any | None = None,
    ) -> None:
        self.row_retention_days = row_retention_days
        self.result_retention_hours = result_retention_hours
        self.pool = pool or ConnectionPool(
            conninfo=database_url,
            min_size=1,
            max_size=10,
            open=False,
            kwargs={"row_factory": dict_row},
        )

    def open(self) -> None:
        self.pool.open(wait=True)

    def close(self) -> None:
        self.pool.close()

    @staticmethod
    def _one(connection: Any, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def health_check(self) -> bool:
        with self.pool.connection() as connection:
            row = self._one(connection, "SELECT 1 AS ready")
        return bool(row and row["ready"] == 1)

    def assert_schema_ready(self) -> None:
        with self.pool.connection() as connection:
            row = self._one(
                connection,
                """
                SELECT to_regclass('nutriathena_agent.schema_migrations') AS ledger,
                       to_regclass('nutriathena_agent.agent_threads') AS threads,
                       to_regclass('nutriathena_agent.agent_runs') AS runs
                """,
            )
        if row is None or any(row[name] is None for name in ("ledger", "threads", "runs")):
            raise RuntimeError("NutriAthenaAgent 数据库迁移尚未应用")

    def create_thread(self, thread_id: UUID, task_id: UUID, attempt_id: UUID) -> dict[str, Any]:
        if thread_id != attempt_id:
            raise ConflictError("thread_id must equal attempt_id")
        with self.pool.connection() as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        f"""
                        INSERT INTO {SCHEMA}.agent_threads (thread_id, task_id, attempt_id)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (attempt_id) DO NOTHING
                        RETURNING *
                        """,
                        (thread_id, task_id, attempt_id),
                    )
                    row = cursor.fetchone()
                    if row is not None:
                        return row
                    cursor.execute(
                        f"""
                        SELECT * FROM {SCHEMA}.agent_threads
                        WHERE attempt_id = %s FOR UPDATE
                        """,
                        (attempt_id,),
                    )
                    existing = cursor.fetchone()
                    if existing is None or existing["thread_id"] != thread_id or existing["task_id"] != task_id:
                        raise ConflictError("thread identity is already bound to different task data")
                    cursor.execute(
                        f"""
                        UPDATE {SCHEMA}.agent_threads
                        SET updated_at = now()
                        WHERE attempt_id = %s
                        RETURNING *
                        """,
                        (attempt_id,),
                    )
                    return cursor.fetchone()

    def get_thread(self, thread_id: UUID) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            return self._one(
                connection,
                f"SELECT * FROM {SCHEMA}.agent_threads WHERE thread_id = %s",
                (thread_id,),
            )

    def submit_run(
        self,
        *,
        thread_id: UUID,
        task_id: UUID,
        attempt_id: UUID,
        release_id: UUID,
        request_payload: dict[str, Any],
        request_sha256: str,
        requested_assistant_id: str,
        requested_artifact_sha256: str,
        deployment_key: str,
        assistant_id: str,
        artifact_sha256: str,
    ) -> tuple[dict[str, Any], bool]:
        run_id = uuid4()
        try:
            with self.pool.connection() as connection:
                with connection.transaction():
                    thread = self._one(
                        connection,
                        f"""
                        SELECT * FROM {SCHEMA}.agent_threads
                        WHERE thread_id = %s AND task_id = %s AND attempt_id = %s FOR UPDATE
                        """,
                        (thread_id, task_id, attempt_id),
                    )
                    if thread is None:
                        raise ConflictError("thread does not match the requested task and attempt")
                    existing = self._one(
                        connection,
                        f"SELECT * FROM {SCHEMA}.agent_runs WHERE attempt_id = %s FOR UPDATE",
                        (attempt_id,),
                    )
                    if existing is not None:
                        if existing["request_sha256"].strip() != request_sha256:
                            raise ConflictError("IDEMPOTENCY_CONFLICT")
                        return existing, False

                    with connection.cursor(row_factory=dict_row) as cursor:
                        cursor.execute(
                            f"""
                            UPDATE {SCHEMA}.agent_threads
                            SET updated_at = now()
                            WHERE attempt_id = %s
                            """,
                            (attempt_id,),
                        )
                        cursor.execute(
                            f"""
                            INSERT INTO {SCHEMA}.agent_runs (
                                run_id, thread_id, task_id, attempt_id, request_payload,
                                release_id, request_sha256, requested_assistant_id,
                                requested_artifact_sha256, agent_deployment_key,
                                agent_assistant_id, agent_artifact_sha256, status
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending'
                            ) RETURNING *
                            """,
                            (
                                run_id,
                                thread_id,
                                task_id,
                                attempt_id,
                                Jsonb(request_payload),
                                release_id,
                                request_sha256,
                                requested_assistant_id,
                                requested_artifact_sha256,
                                deployment_key,
                                assistant_id,
                                artifact_sha256,
                            ),
                        )
                        return cursor.fetchone(), True
        except errors.UniqueViolation:
            existing = self.get_run_by_attempt(attempt_id)
            if existing is None:
                raise
            if existing["request_sha256"].strip() != request_sha256:
                raise ConflictError("IDEMPOTENCY_CONFLICT")
            return existing, False

    def get_run(self, run_id: UUID) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            return self._one(connection, f"SELECT * FROM {SCHEMA}.agent_runs WHERE run_id = %s", (run_id,))

    def get_run_by_attempt(self, attempt_id: UUID) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            return self._one(connection, f"SELECT * FROM {SCHEMA}.agent_runs WHERE attempt_id = %s", (attempt_id,))

    def list_runs(self, thread_id: UUID) -> list[dict[str, Any]]:
        with self.pool.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"SELECT * FROM {SCHEMA}.agent_runs WHERE thread_id = %s ORDER BY created_at, run_id",
                    (thread_id,),
                )
                return cursor.fetchall()

    def interrupt_expired_leases(self) -> int:
        with self.pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE {SCHEMA}.agent_runs
                    SET status = 'interrupted', completed_at = now(),
                        error_code = CASE WHEN cancel_requested_at IS NOT NULL
                            THEN 'CANCELLED' ELSE 'WORKER_LEASE_EXPIRED' END,
                        error_message = CASE WHEN cancel_requested_at IS NOT NULL
                            THEN 'Cancellation was requested.'
                            ELSE 'The worker lease expired; the model call was not replayed.' END,
                        retention_until = now() + %s * INTERVAL '1 day',
                        lease_owner = NULL, lease_expires_at = NULL
                    WHERE status = 'running' AND lease_expires_at <= now()
                    """,
                    (self.row_retention_days,),
                )
                return cursor.rowcount

    def claim_pending(self, owner: str, lease_seconds: int) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            with connection.transaction():
                return self._one(
                    connection,
                    f"""
                    WITH candidate AS (
                        SELECT run_id FROM {SCHEMA}.agent_runs
                        WHERE status = 'pending' AND cancel_requested_at IS NULL
                        ORDER BY created_at, run_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE {SCHEMA}.agent_runs AS run
                    SET status = 'running', started_at = now(),
                        lease_owner = %s,
                        lease_expires_at = now() + %s * INTERVAL '1 second',
                        lease_version = run.lease_version + 1
                    FROM candidate
                    WHERE run.run_id = candidate.run_id
                    RETURNING run.*
                    """,
                    (owner, lease_seconds),
                )

    def renew_lease(self, run_id: UUID, owner: str, version: int, lease_seconds: int) -> tuple[bool, bool]:
        with self.pool.connection() as connection:
            row = self._one(
                connection,
                f"""
                UPDATE {SCHEMA}.agent_runs
                SET lease_expires_at = now() + %s * INTERVAL '1 second'
                WHERE run_id = %s AND status = 'running'
                    AND lease_owner = %s AND lease_version = %s
                    AND lease_expires_at > now()
                RETURNING cancel_requested_at
                """,
                (lease_seconds, run_id, owner, version),
            )
        if row is None:
            return False, False
        return True, row["cancel_requested_at"] is not None

    def finish_success(
        self,
        run_id: UUID,
        owner: str,
        version: int,
        result_payload: dict[str, Any],
        result_sha256: str,
    ) -> bool:
        with self.pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE {SCHEMA}.agent_runs
                    SET status = CASE WHEN cancel_requested_at IS NULL THEN 'success' ELSE 'interrupted' END,
                        result_payload = CASE WHEN cancel_requested_at IS NULL THEN %s ELSE NULL END,
                        result_sha256 = CASE WHEN cancel_requested_at IS NULL THEN %s ELSE NULL END,
                        error_code = CASE WHEN cancel_requested_at IS NULL THEN NULL ELSE 'CANCELLED' END,
                        error_message = CASE WHEN cancel_requested_at IS NULL
                            THEN NULL ELSE 'Cancellation was requested.' END,
                        completed_at = now(),
                        result_expires_at = CASE WHEN cancel_requested_at IS NULL
                            THEN now() + %s * INTERVAL '1 hour' ELSE NULL END,
                        retention_until = now() + %s * INTERVAL '1 day',
                        lease_owner = NULL, lease_expires_at = NULL
                    WHERE run_id = %s AND status = 'running'
                        AND lease_owner = %s AND lease_version = %s
                        AND lease_expires_at > now()
                    RETURNING status
                    """,
                    (
                        Jsonb(result_payload), result_sha256, self.result_retention_hours,
                        self.row_retention_days, run_id, owner, version,
                    ),
                )
                row = cursor.fetchone()
                return row is not None and row["status"] == "success"

    def finish_terminal(
        self,
        run_id: UUID,
        owner: str,
        version: int,
        *,
        status: str,
        error_code: str,
        error_message: str,
    ) -> bool:
        if status not in {"error", "interrupted"}:
            raise ValueError("terminal status must be error or interrupted")
        with self.pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE {SCHEMA}.agent_runs
                    SET status = CASE WHEN cancel_requested_at IS NULL THEN %s ELSE 'interrupted' END,
                        completed_at = now(),
                        error_code = CASE WHEN cancel_requested_at IS NULL THEN %s ELSE 'CANCELLED' END,
                        error_message = CASE WHEN cancel_requested_at IS NULL
                            THEN %s ELSE 'Cancellation was requested.' END,
                        retention_until = now() + %s * INTERVAL '1 day',
                        lease_owner = NULL, lease_expires_at = NULL
                    WHERE run_id = %s AND status = 'running'
                        AND lease_owner = %s AND lease_version = %s
                        AND lease_expires_at > now()
                    """,
                    (status, error_code, error_message, self.row_retention_days, run_id, owner, version),
                )
                return cursor.rowcount == 1

    def request_cancel(self, run_id: UUID) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            with connection.transaction():
                row = self._one(
                    connection,
                    f"""
                    UPDATE {SCHEMA}.agent_runs
                    SET cancel_requested_at = COALESCE(cancel_requested_at, now()),
                        status = CASE WHEN status = 'pending' THEN 'interrupted' ELSE status END,
                        completed_at = CASE WHEN status = 'pending' THEN now() ELSE completed_at END,
                        retention_until = CASE WHEN status = 'pending'
                            THEN now() + %s * INTERVAL '1 day' ELSE retention_until END,
                        error_code = CASE WHEN status = 'pending' THEN 'CANCELLED' ELSE error_code END,
                        error_message = CASE WHEN status = 'pending'
                            THEN 'Cancellation was requested before the run started.' ELSE error_message END
                    WHERE run_id = %s AND status IN ('pending', 'running')
                    RETURNING *
                    """,
                    (self.row_retention_days, run_id),
                )
                return row or self._one(
                    connection,
                    f"SELECT * FROM {SCHEMA}.agent_runs WHERE run_id = %s",
                    (run_id,),
                )

    def purge_expired_results(self) -> int:
        with self.pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE {SCHEMA}.agent_runs
                    SET result_payload = NULL, result_sha256 = NULL, result_purged_at = now()
                    WHERE status = 'success' AND result_purged_at IS NULL
                        AND result_expires_at <= now()
                    """
                )
                return cursor.rowcount

    def purge_expired_rows(self) -> tuple[int, int]:
        with self.pool.connection() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"DELETE FROM {SCHEMA}.agent_runs WHERE retention_until IS NOT NULL AND retention_until <= now()"
                    )
                    runs = cursor.rowcount
                    cursor.execute(
                        f"""
                        DELETE FROM {SCHEMA}.agent_threads AS thread
                        WHERE thread.created_at <= now() - %s * INTERVAL '1 day'
                            AND NOT EXISTS (
                                SELECT 1 FROM {SCHEMA}.agent_runs AS run
                                WHERE run.thread_id = thread.thread_id
                            )
                        """,
                        (self.row_retention_days,),
                    )
                    threads = cursor.rowcount
                    return runs, threads
