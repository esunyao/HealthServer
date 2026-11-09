from __future__ import annotations

import hashlib

from nutriathena_agent.runtime.paths import MIGRATIONS_ROOT
from nutriathena_agent.storage.migrations import _checksum_matches


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
