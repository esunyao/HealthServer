import json
import os
import getpass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import portalocker

from .security import redact


class AuditLog:
    """本地操作审计：写入 JSONL（portalocker 串行化），并提供倒序读取。"""

    def __init__(self, path: Path):
        self.path = path

    def write(self, action: str, target: str, reason: str, outcome: str, **details: Any) -> str:
        operation_id = str(details.pop("operation_id", uuid4_hex()))
        entry = {
            "operation_id": operation_id,
            "occurred_at": datetime.now(UTC).isoformat(),
            "actor": getpass.getuser(),
            "action": action,
            "target": target,
            "reason": reason,
            "outcome": outcome,
            "details": redact(details),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(self.path, "a", timeout=5, encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return operation_id

    def tail(self, limit: int = 100, action: str | None = None, outcome: str | None = None,
             operation_id: str | None = None) -> list[dict[str, Any]]:
        """从文件尾部倒序读取，支持轻量过滤；文件不存在返回空列表。"""
        if not self.path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with open(self.path, encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if action and entry.get("action") != action:
                    continue
                if outcome and entry.get("outcome") != outcome:
                    continue
                if operation_id and entry.get("operation_id") != operation_id:
                    continue
                entries.append(entry)
        return list(reversed(entries))[:limit]


def uuid4_hex() -> str:
    import uuid
    return str(uuid.uuid4())
