import hashlib
import re
from typing import Any

from pglast import parse_sql


BLOCKED = re.compile(r"^\s*(BEGIN|START\s+TRANSACTION|COMMIT|ROLLBACK|SAVEPOINT|RELEASE|COPY|VACUUM|CLUSTER|REINDEX)\b", re.I)


class ExpertSqlService:
    def __init__(self, database):
        self.db = database

    @staticmethod
    def analyze(sql: str) -> dict[str, Any]:
        text = sql.strip()
        if not text:
            raise ValueError("SQL 不能为空")
        statements = parse_sql(text)
        if len(statements) != 1:
            raise ValueError("一次只允许一条 SQL 语句")
        if BLOCKED.search(text) or "\\" in text:
            raise ValueError("禁止事务控制、COPY/维护命令和客户端反斜杠命令")
        kind = re.match(r"^\s*([A-Za-z]+)", text)
        statement_class = kind.group(1).upper() if kind else "UNKNOWN"
        return {
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "sha8": hashlib.sha256(text.encode("utf-8")).hexdigest()[:8],
            "statement_class": statement_class,
            "mutating": statement_class not in {"SELECT", "SHOW", "EXPLAIN", "VALUES"},
        }

    async def preview(self, sql: str) -> dict[str, Any]:
        info = self.analyze(sql)
        async with self.db.preview_transaction() as conn:
            cur = await conn.execute(sql)
            rows = list(await cur.fetchmany(100)) if cur.description else []
            info.update(rows=rows, row_count=cur.rowcount, columns=[c.name for c in cur.description] if cur.description else [])
        return info

    async def execute(self, sql: str) -> dict[str, Any]:
        info = self.analyze(sql)
        async with self.db.transaction() as conn:
            cur = await conn.execute(sql)
            rows = list(await cur.fetchmany(100)) if cur.description else []
            info.update(rows=rows, row_count=cur.rowcount, columns=[c.name for c in cur.description] if cur.description else [])
        return info
