from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from ..config import Settings


REQUIRED_TABLES = {
    "healthmind.ai_tasks", "healthmind.ai_task_attempts", "healthmind.workflow_releases",
    "healthmind.integration_inbox", "healthmind.integration_outbox",
    "nutri.integration_inbox", "nutri.integration_outbox", "nutri.meal_capture_sessions",
}


class Database:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.pool: AsyncConnectionPool | None = None
        self.write_enabled = False
        self.schema_error: str | None = None

    async def open(self) -> None:
        if not self.cfg.database_dsn:
            self.schema_error = "HMC_DATABASE_DSN 未配置"
            return
        self.pool = AsyncConnectionPool(
            self.cfg.database_dsn,
            min_size=1,
            max_size=6,
            timeout=5,
            kwargs={"autocommit": True, "row_factory": dict_row},
            open=False,
        )
        try:
            await self.pool.open()
            await self.verify_schema()
        except Exception as exc:
            self.schema_error = f"数据库连接失败: {exc}"
            self.write_enabled = False
            await self.pool.close()
            self.pool = None

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def verify_schema(self) -> None:
        rows = await self.fetch_all(
            "SELECT table_schema||'.'||table_name AS name FROM information_schema.tables "
            "WHERE table_schema IN ('healthmind','nutri')"
        )
        missing = REQUIRED_TABLES - {row["name"] for row in rows}
        self.write_enabled = not missing
        self.schema_error = f"缺少数据表: {', '.join(sorted(missing))}" if missing else None

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SET statement_timeout='15s'")
                await cur.execute(sql, params)
                return list(await cur.fetchall())

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = await self.fetch_all(sql, params)
        return rows[0] if rows else None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        if not self.pool or not self.write_enabled:
            raise RuntimeError(self.schema_error or "数据库写入未启用")
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute("SET LOCAL lock_timeout='3s'")
                await conn.execute("SET LOCAL statement_timeout='15s'")
                yield conn
