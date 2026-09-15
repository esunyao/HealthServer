import asyncio
import time
from contextlib import asynccontextmanager, suppress
from typing import Any, AsyncIterator

from psycopg import InterfaceError, OperationalError
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from ..config import Settings


REQUIRED_TABLES = {
    "healthmind.ai_tasks", "healthmind.ai_task_attempts", "healthmind.workflow_releases",
    "healthmind.integration_inbox", "healthmind.integration_outbox",
    "nutri.integration_inbox", "nutri.integration_outbox", "nutri.meal_capture_sessions",
}

REQUIRED_COLUMNS = {
    "healthmind.ai_tasks": {"task_id", "task_type_id", "workflow_release_id", "status", "lock_version", "context_manifest"},
    "healthmind.ai_task_attempts": {"attempt_id", "task_id", "attempt_no", "status", "timeout_ms"},
    "healthmind.workflow_releases": {"release_id", "task_type_id", "status", "input_schema", "output_schema"},
    "healthmind.integration_outbox": {"event_id", "task_id", "status", "payload", "next_attempt_at"},
    "nutri.integration_outbox": {"event_id", "aggregate_id", "status", "payload", "next_attempt_at", "locked_at"},
}


class Database:
    """连接池 + 表结构自检。

    启动不阻塞：连接池异步打开，自检放到后台任务并在失败时自动重试，
    避免“启动瞬间连不上 → 关闭一个仍在建连的池”导致 psycopg_pool
    输出 couldn't stop task 'pool-1-worker-N' 之类的噪声。
    """

    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.pool: AsyncConnectionPool | None = None
        self.write_enabled = False
        self.connected = False       # 最近一次数据库交互是否成功（卡片据此显示真实健康度）
        self.schema_error: str | None = None
        self.write_features: dict[str, bool] = {
            "recovery": False, "releases": False, "debug": False, "expert": False, "fixtures": False,
        }
        self._probe_task: asyncio.Task | None = None
        self._down_until = 0.0   # 熔断：连接失败后短时间内直接快速失败，避免多查询叠加超时

    async def open(self) -> None:
        if not self.cfg.database_dsn:
            self.schema_error = "HMC_DATABASE_DSN 未配置"
            return
        self.pool = AsyncConnectionPool(
            self.cfg.database_dsn,
            min_size=self.cfg.database_pool_min_size,
            max_size=self.cfg.database_pool_max_size,
            timeout=3,
            # statement_timeout 通过连接 options 下发：每条查询只发一条命令，
            # 避免客户端中途取消时留下 "another command is already in progress"
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
                "options": "-c statement_timeout=15000 -c application_name=HealthMindControl",
                # 连接握手留出余量（跨网/VPN 偶发慢握手），页面响应速度由获取连接的
                # timeout=3 + 熔断窗口保证，不会因为握手慢而叠加成十几秒
                "connect_timeout": 10,
            },
            open=False,
        )
        await self.pool.open(wait=False)
        self._probe_task = asyncio.create_task(self._verify_schema_loop())

    async def _verify_schema_loop(self) -> None:
        """后台自检：连接成功后校验表结构；连接失败则每 5 秒重试（控制台照常可用）。"""
        while True:
            try:
                await self.verify_schema()
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.write_enabled = False
                self.schema_error = f"数据库连接失败（自动重试中）: {exc}"
                await asyncio.sleep(5)

    async def close(self) -> None:
        if self._probe_task:
            self._probe_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._probe_task
            self._probe_task = None
        if self.pool:
            with suppress(Exception):
                await self.pool.close()

    async def verify_schema(self) -> None:
        if self.cfg.nutri_database_dsn and self.cfg.nutri_database_dsn != self.cfg.database_dsn:
            self.connected = True
            self.write_enabled = False
            self.write_features = {key: False for key in self.write_features}
            self.schema_error = "当前版本不允许跨数据库直接写修复；请将 healthmind/nutri 配置为同一 PostgreSQL DSN"
            return
        rows = await self.fetch_all(
            "SELECT table_schema||'.'||table_name AS name FROM information_schema.tables "
            "WHERE table_schema IN ('healthmind','nutri')",
            strict=True,
        )
        self.connected = True
        missing = REQUIRED_TABLES - {row["name"] for row in rows}
        column_rows = await self.fetch_all(
            "SELECT table_schema||'.'||table_name AS name, column_name FROM information_schema.columns "
            "WHERE table_schema IN ('healthmind','nutri')", strict=True,
        )
        existing: dict[str, set[str]] = {}
        for row in column_rows:
            existing.setdefault(row["name"], set()).add(row["column_name"])
        missing_columns = {
            name: sorted(columns - existing.get(name, set()))
            for name, columns in REQUIRED_COLUMNS.items() if columns - existing.get(name, set())
        }
        audit_check = await self.fetch_one("""
          SELECT pg_get_constraintdef(c.oid) AS definition
          FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
          WHERE n.nspname='healthmind' AND t.relname='workflow_release_audits'
            AND c.contype='c' AND pg_get_constraintdef(c.oid) ILIKE '%%tools_bound%%'
        """)
        base_compatible = self.pool is not None and not missing and not missing_columns
        self.write_enabled = base_compatible
        self.write_features = {
            "recovery": base_compatible, "debug": base_compatible,
            "expert": base_compatible, "fixtures": base_compatible,
            "releases": base_compatible and bool(audit_check),
        }
        if missing:
            self.schema_error = f"缺少数据表: {', '.join(sorted(missing))}"
        elif missing_columns:
            self.schema_error = "字段不兼容: " + "; ".join(f"{k}({','.join(v)})" for k, v in missing_columns.items())
        else:
            self.schema_error = None if audit_check else "版本写入已禁用：workflow_release_audits 缺少 tools_bound(V3) 约束"

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = (), strict: bool = False) -> list[dict[str, Any]]:
        """执行只读查询。

        strict=False（默认）时把“数据库不可用”降级为空结果并记录 schema_error，
        保证控制台在数据库抖动时仍能渲染页面；strict=True 用于自检，异常照常抛出。
        """
        if not self.pool:
            return []
        if not strict and time.monotonic() < self._down_until:
            return []      # 熔断窗口内直接返回空结果，避免每个查询各等一次连接超时
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, params)
                    rows = list(await cur.fetchall())
            self._down_until = 0.0
            self.connected = True
            return rows
        except (OperationalError, InterfaceError, PoolTimeout) as exc:
            if strict:
                raise
            self.write_enabled = False
            self.connected = False
            self._down_until = time.monotonic() + 5
            self.schema_error = f"数据库查询失败: {exc}"
            return []

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = await self.fetch_all(sql, params)
        return rows[0] if rows else None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        if not self.pool or not self.write_enabled:
            raise RuntimeError(self.schema_error or "数据库写入未启用")
        try:
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute("SET LOCAL lock_timeout='3s'")
                    await conn.execute("SET LOCAL statement_timeout='15s'")
                    yield conn
        except (OperationalError, InterfaceError, PoolTimeout) as exc:
            raise RuntimeError(f"数据库不可用: {exc}") from exc

    @asynccontextmanager
    async def preview_transaction(self) -> AsyncIterator[Any]:
        """Always roll back: used by the expert SQL preview executor."""
        if not self.pool or not self.write_enabled:
            raise RuntimeError(self.schema_error or "数据库写入未启用")
        async with self.pool.connection() as conn:
            tx = conn.transaction()
            await tx.__aenter__()
            try:
                await conn.execute("SET LOCAL lock_timeout='3s'")
                await conn.execute("SET LOCAL statement_timeout='15s'")
                yield conn
            finally:
                await tx.__aexit__(RuntimeError, RuntimeError("preview rollback"), None)
