"""Run submission, request idempotency, reads, and cancellation requests."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..execution.types import ConflictError
from .migrations import SCHEMA
from .pool import ConnectionStore


class RunStore(ConnectionStore):
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
                        raise ConflictError(
                            "thread does not match the requested task and attempt"
                        )
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
            return self._one(
                connection,
                f"SELECT * FROM {SCHEMA}.agent_runs WHERE run_id = %s",
                (run_id,),
            )

    def get_run_by_attempt(self, attempt_id: UUID) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            return self._one(
                connection,
                f"SELECT * FROM {SCHEMA}.agent_runs WHERE attempt_id = %s",
                (attempt_id,),
            )

    def list_runs(self, thread_id: UUID) -> list[dict[str, Any]]:
        with self.pool.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"SELECT * FROM {SCHEMA}.agent_runs WHERE thread_id = %s ORDER BY created_at, run_id",
                    (thread_id,),
                )
                return cursor.fetchall()

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
