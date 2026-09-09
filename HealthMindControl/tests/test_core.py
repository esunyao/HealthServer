import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from healthmind_control.security import PreviewStore, canonical_json, redact, sha256_json
from healthmind_control.services import KafkaService
from healthmind_control.util import decode_cursor, encode_cursor


def test_canonical_json_is_recursive_and_utf8():
    assert canonical_json({"z": [{"b": 1, "a": "餐"}], "a": 2}) == '{"a":2,"z":[{"a":"餐","b":1}]}'
    assert sha256_json({"b": 1, "a": 2}) == sha256_json({"a": 2, "b": 1})


def test_redaction():
    assert redact({"Authorization": "Bearer secret", "url": "https://x/a?X-Amz-Signature=secret"}) == {"Authorization": "***", "url": "https://x/a?REDACTED"}


def test_preview_single_use_and_action_bound():
    store = PreviewStore(120)
    token, preview = store.create("task.retry", {"id": "1"}, {"status": "failed"})
    assert store.consume(token, "task.retry") == preview
    with pytest.raises(HTTPException):
        store.consume(token, "task.retry")


def test_business_event_validation():
    service = object.__new__(KafkaService)
    assert service.validate_event("other", "raw") == []
    warnings = service.validate_event("nutrition-capture-ready", {})
    assert warnings and "event_id" in warnings[0]
    event = {k: "x" for k in ("event_id", "event_type", "producer", "trace_id", "schema_version")}
    event["event_type"] = "nutrition.capture.ready.v1"
    event["schema_version"] = "1.0"
    event["payload"] = {}
    assert service.validate_event("nutrition-capture-ready", event) == []
    # 非业务 topic：对象但缺少事件结构 → 警告；纯文本 → 不警告
    assert service.validate_event("some.raw.topic", {"hello": 1}) != []
    assert service.validate_event("some.raw.topic", "plain text") == []


def test_cursor_roundtrip():
    encoded = encode_cursor("2026-09-01T10:00:00+00:00", "uuid-123")
    assert decode_cursor(encoded) == ("2026-09-01T10:00:00+00:00", "uuid-123")
    assert decode_cursor(None) is None
    assert decode_cursor("!!!not-valid!!!") is None


def test_browser_javascript_parses():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    root = Path(__file__).parents[1] / "src" / "healthmind_control" / "static" / "js"
    scripts = sorted(p for p in root.rglob("*.js") if p.is_file())
    if not scripts:
        pytest.skip("no js modules yet")
    # 用仓库内被 gitignore 的 var 目录做探测副本（Windows 临时目录清理偶发权限冲突）
    tmp = Path(__file__).parents[1] / "var" / "tmp-jscheck"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        for script in scripts:
            probe = tmp / script.relative_to(root).with_suffix(".mjs")
            probe.parent.mkdir(parents=True, exist_ok=True)
            probe.write_bytes(script.read_bytes())
            subprocess.run([node, "--check", str(probe)], check=True, capture_output=True, text=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
