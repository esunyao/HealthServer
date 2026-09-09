from typing import Any

from ..db import Database


class BaseRepository:
    """各领域 mixin 的公共基座：共享数据库句柄与受控快照读取。"""

    def __init__(self, db: Database, stale_minutes: int = 5, retention_days: int = 180):
        self.db = db
        self.stale_minutes = stale_minutes
        self.retention_days = retention_days

    async def snapshot(self, table: str, column: str, value: str) -> dict[str, Any] | None:
        """只允许在固定（表, 主键列）集合内读取行快照，供预览绑定版本。"""
        allowed = {
            ("healthmind.ai_tasks", "task_id"), ("healthmind.ai_task_attempts", "attempt_id"),
            ("healthmind.integration_outbox", "event_id"), ("nutri.integration_outbox", "event_id"),
            ("nutri.integration_inbox", "event_id"),
            ("healthmind.workflow_releases", "release_id"),
        }
        if (table, column) not in allowed:
            raise ValueError("unsupported snapshot")
        return await self.db.fetch_one(f"SELECT * FROM {table} WHERE {column}=%s", (value,))
