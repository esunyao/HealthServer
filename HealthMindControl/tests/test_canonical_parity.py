"""Canonical/hash 与 HealthMind Kotlin 实现的对照测试。

做法：从 HealthMind V2 seed migration 原样抽取 $tool$...$tool$::jsonb 内嵌的
JSON schema 字面量与紧随其后的 64 位十六进制 sha256 列，用 Python 侧 canonical
实现重新计算并逐字比对，防止两端 canonical 语义漂移。
"""
import json
import re
from pathlib import Path

from healthmind_control.security import sha256_json

MIGRATION = Path(__file__).resolve().parents[2] / "HealthMind" / "src" / "main" / "resources" / "db" / "migration" / "V2__seed_stable_definitions.sql"


def test_schema_hashes_match_kotlin_seed_values():
    text = MIGRATION.read_text(encoding="utf-8")
    pattern = re.compile(r"\$tool\$(.*?)\$tool\$::jsonb", re.DOTALL)
    hex_pattern = re.compile(r"[0-9a-f]{64}")
    matches = list(pattern.finditer(text))
    assert matches, "seed migration 中应存在 $tool$ 字面量"
    checked = 0
    for match in matches:
        literal = match.group(1)
        schema = json.loads(literal)
        following = text[match.end(): match.end() + 300]
        stored = hex_pattern.search(following)
        assert stored, "字面量后 300 字符内应有 sha256 列"
        assert sha256_json(schema) == stored.group(0), f"canonical sha 与 seed 不一致: {literal[:60]}..."
        checked += 1
    assert checked >= 2
