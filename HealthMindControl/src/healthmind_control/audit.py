import json
import os
import getpass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import portalocker

from .security import redact


class AuditLog:
    def __init__(self, path: Path):
        self.path = path

    def write(self, action: str, target: str, reason: str, outcome: str, **details: Any) -> str:
        operation_id = str(details.pop("operation_id", uuid4()))
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

