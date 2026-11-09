"""Attempt-bound thread identity and idempotent thread creation."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from ..execution.types import ConflictError
from .migrations import SCHEMA
from .pool import ConnectionStore


class ThreadStore(ConnectionStore):
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
