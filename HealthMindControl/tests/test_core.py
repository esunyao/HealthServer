import json
import time

import pytest
from fastapi import HTTPException

from healthmind_control.kafka import KafkaService
from healthmind_control.security import PreviewStore, canonical_json, redact, sha256_json


def test_canonical_json_is_recursive_and_utf8():
    assert canonical_json({"z": [{"b": 1, "a": "餐"}], "a": 2}) == '{"a":2,"z":[{"a":"餐","b":1}]}'
    assert sha256_json({"b": 1, "a": 2}) == sha256_json({"a": 2, "b": 1})


def test_redaction():
    assert redact({"Authorization": "Bearer secret", "url": "https://x/a?X-Amz-Signature=secret"}) == {"Authorization": "***", "url": "https://x/a?REDACTED"}


def test_preview_single_use_and_action_bound():
    store = PreviewStore(120)
    token, preview = store.create("task.retry", {"id": "1"}, {"status": "failed"})
    assert store.consume(token, "task.retry") == preview
    with pytest.raises(HTTPException): store.consume(token, "task.retry")


def test_business_event_validation():
    service = object.__new__(KafkaService)
    assert service.validate_event("other", "raw") == []
    warnings = service.validate_event("nutrition-capture-ready", {})
    assert warnings and "event_id" in warnings[0]
    event = {k: "x" for k in ("event_id","event_type","producer","trace_id","schema_version")}
    event["payload"] = {}
    assert service.validate_event("nutrition-capture-ready", event) == []

