import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class DebugStore:
    """Local, append-oriented control-plane state. Business data stays in PostgreSQL."""

    def __init__(self, path: Path):
        self.path = path

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS debug_runs (
                run_id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL,
                status TEXT NOT NULL, context_json TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS debug_operations (
                operation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step TEXT NOT NULL,
                action TEXT NOT NULL, status TEXT NOT NULL, detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES debug_runs(run_id)
              );
              CREATE INDEX IF NOT EXISTS idx_debug_operations_run
                ON debug_operations(run_id, created_at);
            """)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def create(self, name: str, mode: str, context: dict[str, Any]) -> dict[str, Any]:
        run_id, now = str(uuid4()), self._now()
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO debug_runs VALUES (?,?,?,?,?,?,?)",
                (run_id, name, mode, "active", json.dumps(context, ensure_ascii=False), now, now),
            )
        return self.get(run_id) or {}

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM debug_runs ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 100)),)
            ).fetchall()
        return [self._run(dict(row)) for row in rows]

    def get(self, run_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM debug_runs WHERE run_id=?", (run_id,)).fetchone()
            operations = db.execute(
                "SELECT * FROM debug_operations WHERE run_id=? ORDER BY created_at", (run_id,)
            ).fetchall()
        if not row:
            return None
        result = self._run(dict(row))
        result["operations"] = [self._operation(dict(item)) for item in operations]
        return result

    def update_context(self, run_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.get(run_id)
        if not current:
            raise KeyError(run_id)
        context = {**current["context"], **patch}
        with sqlite3.connect(self.path) as db:
            db.execute(
                "UPDATE debug_runs SET context_json=?, updated_at=? WHERE run_id=?",
                (json.dumps(context, ensure_ascii=False), self._now(), run_id),
            )
        return self.get(run_id) or {}

    def record(self, run_id: str, step: str, action: str, status: str, detail: Any) -> str:
        operation_id = str(uuid4())
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO debug_operations VALUES (?,?,?,?,?,?,?)",
                (operation_id, run_id, step, action, status,
                 json.dumps(detail, ensure_ascii=False, default=str), self._now()),
            )
            db.execute("UPDATE debug_runs SET updated_at=? WHERE run_id=?", (self._now(), run_id))
        return operation_id

    @staticmethod
    def _run(row: dict[str, Any]) -> dict[str, Any]:
        row["context"] = json.loads(row.pop("context_json"))
        return row

    @staticmethod
    def _operation(row: dict[str, Any]) -> dict[str, Any]:
        row["detail"] = json.loads(row.pop("detail_json"))
        return row
