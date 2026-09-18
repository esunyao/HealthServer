import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from confluent_kafka import Consumer
from fastapi import FastAPI
from fastapi.testclient import TestClient

from healthmind_control.debug_store import DebugStore
from healthmind_control.security import PreviewStore
from healthmind_control.services.expert import ExpertSqlService
from healthmind_control.services.kafka import KafkaService
from healthmind_control.util import serial
from healthmind_control.api.kafka import router as kafka_router


def test_preview_intent_is_copied_and_single_use():
    intent = {"topic": "a", "payload_text": '{"meal_id":2097632617381867522}'}
    store = PreviewStore(120)
    token, _ = store.create("kafka.produce", intent, intent)
    intent["topic"] = "b"
    assert store.consume(token, "kafka.produce").payload["topic"] == "a"


def test_bigint_is_lossless_for_browser():
    value = 2_097_632_617_381_867_522
    assert serial({"meal_id": value}) == {"meal_id": str(value)}
    assert serial({"safe": 42}) == {"safe": 42}


def test_kafka_consumer_uses_librdkafka_property_names():
    service = object.__new__(KafkaService)
    service._base = {"bootstrap.servers": "127.0.0.1:1", "socket.timeout.ms": 10}
    consumer = service._consumer(
        "healthmind-control-test", **{"enable.auto.offset.store": False, "auto.offset.reset": "earliest"}
    )
    assert isinstance(consumer, Consumer)
    consumer.close()


def test_expert_sql_parser_rejects_multiple_and_transaction_control():
    assert ExpertSqlService.analyze("select 1")["statement_class"] == "SELECT"
    with pytest.raises(ValueError, match="一条"):
        ExpertSqlService.analyze("select 1; select 2")
    with pytest.raises(ValueError, match="禁止"):
        ExpertSqlService.analyze("BEGIN")


def test_debug_store_retains_run_and_operations(tmp_path: Path):
    store = DebugStore(tmp_path / "debug.sqlite3")
    store.open()
    run = store.create("manual chain", "mixed", {"meal_id": "2097632617381867522"})
    store.record(run["run_id"], "hold_task", "debug.hold_task", "succeeded", {"task_id": "t"})
    loaded = store.get(run["run_id"])
    assert loaded and loaded["context"]["meal_id"] == "2097632617381867522"
    assert loaded["operations"][0]["step"] == "hold_task"


def test_kafka_execute_uses_server_side_preview_intent():
    class FakeKafka:
        sent = None

        async def metadata(self, force=False):
            return {"topics": [{"name": "topic-a"}, {"name": "topic-b"}], "brokers": []}

        @staticmethod
        def parse_payload(text):
            import json
            return json.loads(text)

        @staticmethod
        def validate_event(topic, payload):
            return []

        async def produce(self, topic, key, payload, headers, partition):
            self.sent = (topic, key, payload, headers, partition)
            return {"offset": 1, "partition": 0}

    class FakeAudit:
        async def write(self, *args, **kwargs):
            return "op"

    app = FastAPI()
    app.include_router(kafka_router)
    app.state.csrf_token = "csrf"
    app.state.previews = PreviewStore(120)
    app.state.kafka = FakeKafka()
    app.state.audit = FakeAudit()
    app.state.settings = SimpleNamespace(enable_expert_mode=False)
    with TestClient(app) as client:
        preview = client.post("/api/kafka/produce/preview", json={
            "csrf_token": "csrf", "reason": "test intent", "topic": "topic-a",
            "key": "original", "payload_text": "2097632617381867522",
        }).json()
        response = client.post("/api/kafka/produce/execute", json={
            "csrf_token": "csrf", "preview_token": preview["preview_token"],
            "confirmation": "PRODUCE topic-a", "topic": "topic-b", "key": "changed",
            "payload_text": "0",
        })
    assert response.status_code == 200
    assert app.state.kafka.sent[:3] == ("topic-a", "original", "2097632617381867522")


def test_kafka_warning_rejection_keeps_preview_reusable():
    class FakeKafka:
        calls = 0

        async def metadata(self, force=False):
            return {"topics": [{"name": "custom-topic"}], "brokers": [{"id": 1}]}

        @staticmethod
        def parse_payload(text):
            import json
            return json.loads(text)

        @staticmethod
        def validate_event(topic, payload):
            return ["non-standard event"]

        async def produce(self, *args):
            self.calls += 1
            return {"offset": 7, "partition": 0}

    class FakeAudit:
        async def write(self, *args, **kwargs):
            return kwargs.get("operation_id", "op")

    app = FastAPI()
    app.include_router(kafka_router)
    app.state.csrf_token = "csrf"
    app.state.previews = PreviewStore(120)
    app.state.kafka = FakeKafka()
    app.state.audit = FakeAudit()
    app.state.settings = SimpleNamespace(enable_expert_mode=False)
    with TestClient(app) as client:
        preview = client.post("/api/kafka/produce/preview", json={
            "csrf_token": "csrf", "reason": "warning retry", "topic": "custom-topic",
            "payload_text": "{}",
        }).json()
        rejected = client.post("/api/kafka/produce/execute", json={
            "csrf_token": "csrf", "preview_token": preview["preview_token"],
            "confirmation": "PRODUCE custom-topic", "accept_warnings": False,
        })
        accepted = client.post("/api/kafka/produce/execute", json={
            "csrf_token": "csrf", "preview_token": preview["preview_token"],
            "confirmation": "PRODUCE custom-topic", "accept_warnings": True,
        })
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "WARNINGS_NOT_ACCEPTED"
    assert accepted.status_code == 200
    assert app.state.kafka.calls == 1
