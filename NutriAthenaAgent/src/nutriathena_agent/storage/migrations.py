"""Checksum-verified SQL migrations for the isolated agent schema."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from time import perf_counter
from typing import Any

from psycopg.rows import dict_row

from ..observability import log_event
from ..runtime.paths import MIGRATIONS_ROOT

SCHEMA = "nutriathena_agent"
MIGRATIONS_DIR = MIGRATIONS_ROOT
_MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

# The original 0001 was applied from Windows with CRLF, while Git stores LF.
# These exact known hashes differ only in line endings; no other bytes qualify.
_LEGACY_CHECKSUM_EQUIVALENTS = {
    "0001_create_agent_runtime.sql": frozenset(
        {
            "f3b079ca7328b288795c6825fdb76c9394987bcf230774533e46ff8ae1101607",
            "f660e6b7c6dc6fa20a76df94828289e602673356dce1c72eebc7b36574d2719c",
        }
    ),
}


def _checksum_matches(script_name: str, actual: str, recorded: str) -> bool:
    if actual == recorded:
        return True
    equivalents = _LEGACY_CHECKSUM_EQUIVALENTS.get(script_name, frozenset())
    return actual in equivalents and recorded in equivalents


class MigrationError(RuntimeError):
    """A migration is missing, changed after apply, or cannot be applied."""


def apply_migrations(pool: Any, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    scripts: list[tuple[int, Path, str, str]] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(
                f"迁移文件名必须为 4 位版本号_小写名称.sql：{path.name}"
            )
        raw = path.read_bytes()
        try:
            sql = raw.decode("utf-8")
        except UnicodeDecodeError as exception:
            raise MigrationError(f"迁移文件不是 UTF-8：{path.name}") from exception
        scripts.append(
            (int(match.group(1)), path, sql, hashlib.sha256(raw).hexdigest())
        )

    if not scripts:
        raise MigrationError("没有找到 NutriAthenaAgent SQL 迁移文件")
    if len({version for version, *_ in scripts}) != len(scripts):
        raise MigrationError("NutriAthenaAgent 迁移版本号重复")

    with pool.connection() as connection:
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA}.schema_migrations (
                version INTEGER PRIMARY KEY,
                script_name VARCHAR(255) NOT NULL UNIQUE,
                checksum_sha256 CHAR(64) NOT NULL
                    CHECK (checksum_sha256 ~ '^[0-9a-f]{{64}}$'),
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                execution_ms BIGINT NOT NULL CHECK (execution_ms >= 0)
            )
            """
        )

    applied_names: list[str] = []
    applied_details: list[tuple[str, int, int]] = []
    with pool.connection() as connection:
        with connection.transaction():
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                # Stable across runtime versions; unrelated to Python import paths.
                ("nutriathena_agent.migrations",),
            )
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"SELECT version, script_name, checksum_sha256 FROM {SCHEMA}.schema_migrations"
                )
                applied = {row["version"]: row for row in cursor.fetchall()}
                known_versions = {version for version, *_ in scripts}
                unknown = sorted(set(applied) - known_versions)
                if unknown:
                    raise MigrationError(
                        f"数据库包含当前代码不认识的迁移版本：{unknown}"
                    )

                for version, path, sql, checksum in scripts:
                    existing = applied.get(version)
                    if existing is not None:
                        recorded_checksum = existing["checksum_sha256"].strip()
                        if existing[
                            "script_name"
                        ] != path.name or not _checksum_matches(
                            path.name, checksum, recorded_checksum
                        ):
                            raise MigrationError(
                                f"已应用的迁移文件或校验和发生变化：{path.name}"
                            )
                        if recorded_checksum != checksum:
                            log_event(
                                "migration.checksum.line_endings_compatible",
                                level="WARNING",
                                file=path.name,
                                version=version,
                            )
                        log_event(
                            "migration.skipped",
                            level="DEBUG",
                            file=path.name,
                            version=version,
                        )
                        continue

                    log_event(
                        "migration.applying",
                        level="INFO",
                        file=path.name,
                        version=version,
                    )
                    started = perf_counter()
                    cursor.execute(sql, prepare=False)
                    elapsed_ms = max(0, int((perf_counter() - started) * 1000))
                    cursor.execute(
                        f"""
                        INSERT INTO {SCHEMA}.schema_migrations
                            (version, script_name, checksum_sha256, execution_ms)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (version, path.name, checksum, elapsed_ms),
                    )
                    applied_details.append((path.name, version, elapsed_ms))
                    applied_names.append(path.name)
    for script_name, version, elapsed_ms in applied_details:
        log_event(
            "migration.applied",
            level="INFO",
            file=script_name,
            version=version,
            duration_ms=elapsed_ms,
        )
    return applied_names
