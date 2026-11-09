"""Result expiry and ordered deletion of run and thread tombstones."""

from __future__ import annotations

from .migrations import SCHEMA
from .pool import ConnectionStore


class RetentionStore(ConnectionStore):
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
