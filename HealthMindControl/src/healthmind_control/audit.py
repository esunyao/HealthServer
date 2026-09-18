import asyncio
import json
import os
import getpass
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import portalocker

from .security import redact


class AuditLog:
    """本地操作审计：写入 JSONL（portalocker 串行化），并提供倒序读取。"""

    _ROTATED_RE = re.compile(r"^admin-actions\.(\d{8}T\d{6}Z)\.(\d+)\.jsonl$")

    def __init__(self, path: Path, *, rotate_bytes: int = 50 * 1024 * 1024, retention_days: int = 90):
        self.path = path
        self.rotate_bytes = rotate_bytes
        self.retention_days = retention_days

    async def write(self, action: str, target: str, reason: str, outcome: str, **details: Any) -> str:
        return await asyncio.to_thread(self._write, action, target, reason, outcome, details)

    def _write(self, action: str, target: str, reason: str, outcome: str, details: dict[str, Any]) -> str:
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
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with portalocker.Lock(lock_path, "a", timeout=5, encoding="utf-8"):
            self._rotate_if_needed()
            self._cleanup_rotated()
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return operation_id

    def _rotate_if_needed(self) -> None:
        if not self.path.exists() or self.path.stat().st_size < self.rotate_bytes:
            return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        sequence = 1
        while True:
            rotated = self.path.with_name(f"admin-actions.{stamp}.{sequence}.jsonl")
            if not rotated.exists():
                self.path.replace(rotated)
                return
            sequence += 1

    def _cleanup_rotated(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        for candidate in self.path.parent.glob("admin-actions.*.jsonl"):
            if candidate == self.path or not self._ROTATED_RE.match(candidate.name):
                continue
            try:
                if datetime.fromtimestamp(candidate.stat().st_mtime, UTC) < cutoff:
                    candidate.unlink()
            except OSError:
                # Audit availability takes precedence over retention housekeeping.
                continue

    async def tail(self, limit: int = 100, action: str | None = None, outcome: str | None = None,
                   operation_id: str | None = None) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._tail, limit, action, outcome, operation_id)

    def _tail(self, limit: int, action: str | None, outcome: str | None,
              operation_id: str | None) -> list[dict[str, Any]]:
        """Read newest matching JSONL records without materialising whole audit files."""
        limit = max(1, min(limit, 1000))
        entries: list[dict[str, Any]] = []
        files = [self.path]
        files.extend(sorted(
            (item for item in self.path.parent.glob("admin-actions.*.jsonl")
             if self._ROTATED_RE.match(item.name)),
            key=lambda item: item.name,
            reverse=True,
        ))
        for file_path in files:
            if not file_path.exists():
                continue
            for raw in self._reverse_lines(file_path):
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
                if len(entries) >= limit:
                    return entries
        return entries

    @staticmethod
    def _reverse_lines(path: Path, block_size: int = 65536):
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            position, remainder = handle.tell(), b""
            while position:
                read_size = min(block_size, position)
                position -= read_size
                handle.seek(position)
                data = handle.read(read_size) + remainder
                parts = data.split(b"\n")
                remainder = parts[0]
                for line in reversed(parts[1:]):
                    if line.strip():
                        yield line.decode("utf-8", "replace")
            if remainder.strip():
                yield remainder.decode("utf-8", "replace")


def uuid4_hex() -> str:
    import uuid
    return str(uuid.uuid4())
