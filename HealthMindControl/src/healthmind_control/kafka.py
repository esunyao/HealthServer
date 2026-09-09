import asyncio
import json
from datetime import datetime
from typing import Any

from confluent_kafka import Consumer, ConsumerGroupTopicPartitions, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient

from .config import Settings


BUSINESS_TOPICS = {
    "nutrition-capture-ready",
    "nutrition-analysis-completed",
    "nutrition-analysis-failed",
}


class KafkaService:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        base = {"bootstrap.servers": cfg.kafka_bootstrap_servers, "socket.timeout.ms": 5000}
        self.admin = AdminClient(base)
        self.producer = Producer(base)

    async def metadata(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._metadata)

    def _metadata(self) -> dict[str, Any]:
        md = self.admin.list_topics(timeout=5)
        brokers = [{"id": b.id, "host": b.host, "port": b.port} for b in md.brokers.values()]
        topics = []
        consumer = Consumer({"bootstrap.servers": self.cfg.kafka_bootstrap_servers, "group.id": "healthmind-control-metadata", "enable.auto.commit": False})
        for name, topic in sorted(md.topics.items()):
            if name.startswith("__"):
                continue
            parts = []
            for pid, part in sorted(topic.partitions.items()):
                try:
                    low, high = consumer.get_watermark_offsets(TopicPartition(name, pid), timeout=2)
                except Exception:
                    low, high = None, None
                parts.append({
                    "partition": pid, "leader": part.leader,
                    "replicas": list(part.replicas), "isr": list(part.isrs),
                    "earliest_offset": low, "latest_offset": high,
                    "healthy": part.leader >= 0 and set(part.replicas) == set(part.isrs),
                })
            topics.append({"name": name, "error": str(topic.error) if topic.error else None, "partitions": parts})
        consumer.close()
        return {"brokers": brokers, "topics": topics}

    async def groups(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._groups)

    def _groups(self) -> list[dict[str, Any]]:
        result = self.admin.list_consumer_groups(request_timeout=5).result(6)
        groups = []
        for listing in result.valid:
            item = {"group_id": listing.group_id, "state": str(listing.state), "simple": listing.is_simple_consumer_group, "lag": None}
            try:
                offsets = self.admin.list_consumer_group_offsets([ConsumerGroupTopicPartitions(listing.group_id)], request_timeout=5)[listing.group_id].result(6)
                md = self.admin.list_topics(timeout=5)
                lag = 0
                consumer = Consumer({"bootstrap.servers": self.cfg.kafka_bootstrap_servers, "group.id": "healthmind-control-lag", "enable.auto.commit": False})
                for tp in offsets.topic_partitions:
                    if tp.offset >= 0 and tp.topic in md.topics:
                        _, high = consumer.get_watermark_offsets(TopicPartition(tp.topic, tp.partition), timeout=2)
                        lag += max(0, high - tp.offset)
                consumer.close(); item["lag"] = lag
            except Exception:
                pass
            groups.append(item)
        return groups

    async def messages(
        self, topic: str, partition: int = 0, start: str = "latest", offset: int | None = None,
        limit: int = 50, contains: str | None = None,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._messages, topic, partition, start, offset, min(limit, 100), contains)

    def _messages(self, topic: str, partition: int, start: str, offset: int | None, limit: int, contains: str | None):
        consumer = Consumer({
            "bootstrap.servers": self.cfg.kafka_bootstrap_servers,
            "group.id": f"healthmind-control-diagnostic-{datetime.now().timestamp()}",
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
        })
        try:
            tp = TopicPartition(topic, partition)
            low, high = consumer.get_watermark_offsets(tp, timeout=5)
            target = offset if offset is not None else (low if start == "earliest" else max(low, high - limit))
            consumer.assign([TopicPartition(topic, partition, target)])
            output = []
            empty = 0
            while len(output) < limit and empty < 3:
                msg = consumer.poll(1)
                if msg is None:
                    empty += 1
                    continue
                if msg.error():
                    if msg.error().code() == -191:
                        break
                    raise KafkaException(msg.error())
                raw = msg.value().decode("utf-8", "replace") if msg.value() else ""
                if contains and contains not in raw and contains not in (msg.key() or b"").decode("utf-8", "replace"):
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = raw
                output.append({
                    "topic": msg.topic(), "partition": msg.partition(), "offset": msg.offset(),
                    "timestamp": msg.timestamp()[1],
                    "key": (msg.key() or b"").decode("utf-8", "replace"),
                    "headers": dict(msg.headers() or []), "payload": payload,
                })
            return output
        finally:
            consumer.close()

    def validate_event(self, topic: str, payload: Any) -> list[str]:
        warnings = []
        if topic in BUSINESS_TOPICS:
            required = {"event_id", "event_type", "producer", "trace_id", "schema_version", "payload"}
            if not isinstance(payload, dict):
                warnings.append("业务 topic 的 payload 应为 JSON 对象")
            else:
                missing = sorted(required - payload.keys())
                if missing:
                    warnings.append("缺少业务事件字段: " + ", ".join(missing))
        return warnings

    async def produce(self, topic: str, key: str | None, payload: Any, headers: dict[str, str], partition: int | None):
        return await asyncio.to_thread(self._produce, topic, key, payload, headers, partition)

    def _produce(self, topic: str, key: str | None, payload: Any, headers: dict[str, str], partition: int | None):
        delivered: dict[str, Any] = {}
        def callback(error, message):
            if error:
                delivered["error"] = str(error)
            else:
                delivered.update(topic=message.topic(), partition=message.partition(), offset=message.offset())
        kwargs = {"topic": topic, "key": key, "value": json.dumps(payload, ensure_ascii=False), "headers": list(headers.items()), "callback": callback}
        if partition is not None:
            kwargs["partition"] = partition
        self.producer.produce(**kwargs)
        remaining = self.producer.flush(10)
        if remaining or delivered.get("error"):
            raise RuntimeError(delivered.get("error") or f"{remaining} message(s) undelivered")
        return delivered
