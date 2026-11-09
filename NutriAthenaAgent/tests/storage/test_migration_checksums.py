from __future__ import annotations

import hashlib
from unittest.mock import MagicMock

from nutriathena_agent.runtime.paths import MIGRATIONS_ROOT
from nutriathena_agent.storage.migrations import _checksum_matches, apply_migrations


def test_known_migration_accepts_only_original_lf_and_crlf_variants():
    path = MIGRATIONS_ROOT / "0001_create_agent_runtime.sql"
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    lf = hashlib.sha256(raw).hexdigest()
    crlf = hashlib.sha256(raw.replace(b"\n", b"\r\n")).hexdigest()

    assert _checksum_matches(path.name, lf, crlf)
    assert _checksum_matches(path.name, crlf, lf)
    assert not _checksum_matches("0002_other.sql", lf, crlf)
    altered = hashlib.sha256(raw + b"-- altered\n").hexdigest()
    assert not _checksum_matches(path.name, altered, crlf)
    assert not _checksum_matches(path.name, lf, altered)


def test_identical_checksums_match_for_new_migrations():
    assert _checksum_matches("0002_other.sql", "a" * 64, "a" * 64)
    assert not _checksum_matches("0002_other.sql", "a" * 64, "b" * 64)


def test_migration_lock_remains_compatible_with_previous_runtime_versions(tmp_path):
    script = tmp_path / "0001_lock_test.sql"
    script.write_text("SELECT 1;\n", encoding="utf-8")
    pool = MagicMock()
    connection = pool.connection.return_value.__enter__.return_value
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []

    assert apply_migrations(pool, migrations_dir=tmp_path) == [script.name]

    connection.execute.assert_any_call(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        ("nutriathena_agent.migrations",),
    )
