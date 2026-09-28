from __future__ import annotations

from nutriathena_agent.artifact import compute_artifact_sha256


def test_artifact_digest_is_derived_from_deployed_files(tmp_path):
    root = tmp_path / "module"
    package = root / "src" / "nutriathena_agent"
    migrations = root / "migrations"
    skills = tmp_path / "skills"
    package.mkdir(parents=True)
    migrations.mkdir()
    skills.mkdir()
    (package / "runner.py").write_text("runner-v1", encoding="utf-8")
    (migrations / "0001_init.sql").write_text("create table test();", encoding="utf-8")
    (skills / "SKILL.md").write_text("meal guidance v1", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='test'", encoding="utf-8")
    (root / "uv.lock").write_text("lock-v1", encoding="utf-8")

    first = compute_artifact_sha256(root, skills)
    assert len(first) == 64
    assert first == compute_artifact_sha256(root, skills)

    (package / "runner.py").write_text("runner-v2", encoding="utf-8")
    assert compute_artifact_sha256(root, skills) != first
