"""Connection pool lifecycle, row fetching, and schema readiness."""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class ConnectionStore:
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
