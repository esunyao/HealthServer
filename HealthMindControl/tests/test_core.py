import json
import shutil
import subprocess
import tempfile
import threading
import time
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


def test_preview_state_machine_replays_success_and_blocks_duplicate_execution():
    store = PreviewStore(120)
    token, preview = store.create("task.retry", {"id": "1"}, {"status": "failed"})
    claimed, replayed, result = store.begin(token, "task.retry")
    assert claimed == preview and replayed is False and result is None
    with pytest.raises(HTTPException):
        store.begin(token, "task.retry")
    store.succeed(token, {"task_id": "new"})
    _, replayed, result = store.begin(token, "task.retry")
    assert replayed is True and result == {"task_id": "new"}


def test_preview_release_allows_retry_but_indeterminate_does_not():
    store = PreviewStore(120)
    token, preview = store.create("fixture.write", {}, {})
    store.begin(token, "fixture.write")
    store.release(token, "preflight failed")
    assert store.begin(token, "fixture.write")[0] == preview
    store.indeterminate(token, "commit outcome unknown")
    with pytest.raises(HTTPException) as caught:
        store.begin(token, "fixture.write")
    assert caught.value.detail["code"] == "EXECUTION_INDETERMINATE"


def test_preview_claim_is_atomic_across_threads():
    store = PreviewStore(120)
    token, _ = store.create("fixture.write", {}, {})
    barrier = threading.Barrier(3)
    outcomes = []

    def claim():
        barrier.wait()
        try:
            store.begin(token, "fixture.write")
            outcomes.append("claimed")
        except HTTPException as exc:
            outcomes.append(exc.detail["code"])

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["PREVIEW_EXECUTING", "claimed"]


def test_preview_expiry_requires_new_preview():
    store = PreviewStore(120)
    token, preview = store.create("fixture.write", {}, {})
    preview.expires_at = time.time() - 1
    with pytest.raises(HTTPException) as caught:
        store.inspect(token, "fixture.write")
    assert caught.value.detail["code"] == "PREVIEW_EXPIRED"
    assert caught.value.detail["requires_repreview"] is True


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
