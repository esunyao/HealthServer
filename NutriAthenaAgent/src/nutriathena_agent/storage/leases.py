"""Worker claims, heartbeat renewal, and fenced terminal writes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from .migrations import SCHEMA
from .pool import ConnectionStore


class LeaseStore(ConnectionStore):
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

    def claim_pending(
        self,
        owner: str,
        lease_seconds: int,
        *,
        release_id: UUID,
        deployment_key: str,
        assistant_id: str,
        artifact_sha256: str,
    ) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            with connection.transaction():
                return self._one(
                    connection,
                    f"""
                    WITH candidate AS (
                        SELECT run_id FROM {SCHEMA}.agent_runs
                        WHERE status = 'pending' AND cancel_requested_at IS NULL
                            AND release_id = %s
                            AND agent_deployment_key = %s
                            AND agent_assistant_id = %s
                            AND agent_artifact_sha256 = %s
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
                    (
                        release_id,
                        deployment_key,
                        assistant_id,
                        artifact_sha256,
                        owner,
                        lease_seconds,
                    ),
                )

    def renew_lease(
        self, run_id: UUID, owner: str, version: int, lease_seconds: int
    ) -> tuple[bool, bool]:
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
                        Jsonb(result_payload),
                        result_sha256,
                        self.result_retention_hours,
                        self.row_retention_days,
                        run_id,
                        owner,
                        version,
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
                    (
                        status,
                        error_code,
                        error_message,
                        self.row_retention_days,
                        run_id,
                        owner,
                        version,
                    ),
                )
                return cursor.rowcount == 1
