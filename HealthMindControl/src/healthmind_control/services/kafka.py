import asyncio
import json
import time
from datetime import datetime
from typing import Any

from confluent_kafka import Consumer, ConsumerGroupTopicPartitions, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient

from ..config import Settings


BUSINESS_TOPICS = {
    "nutrition-capture-ready": "nutrition.capture.ready.v1",
    "nutrition-analysis-completed": "nutrition.analysis.completed.v1",
    "nutrition-analysis-failed": "nutrition.analysis.failed.v1",
}

SELF_GROUP_PREFIX = "healthmind-control-"


def build_client_config(cfg: Settings, group_id: str | None = None, consumer: bool = False) -> dict[str, Any]:
    """统一构造 confluent-kafka 客户端配置（含可选 SASL/SSL）。

    - consumer=True 时才注入消费端专有属性（session.timeout.ms），避免 Producer/Admin
      触发 librdkafka 的 CONFWARN 警告；
    - 凭据只来自环境变量/.env（HMC_*），绝不入库/入审计；缺配置时抛出可读错误。
    """
    protocol = (cfg.kafka_security_protocol or "PLAINTEXT").upper()
    base: dict[str, Any] = {
        "bootstrap.servers": cfg.kafka_bootstrap_servers,
        "socket.timeout.ms": 5000,
    }
    if consumer:
        base["session.timeout.ms"] = 6000
    if protocol != "PLAINTEXT":
        base["security.protocol"] = protocol
        if protocol.startswith("SASL"):
            if not cfg.kafka_sasl_username or not cfg.kafka_sasl_password:
                raise RuntimeError(
                    "Kafka 使用 SASL 认证但缺少凭据：请在 .env 配置 HMC_KAFKA_SASL_USERNAME / HMC_KAFKA_SASL_PASSWORD"
                )
            base["sasl.mechanism"] = cfg.kafka_sasl_mechanism or "PLAIN"
            base["sasl.username"] = cfg.kafka_sasl_username
            base["sasl.password"] = cfg.kafka_sasl_password
        if "SSL" in protocol and cfg.kafka_ssl_ca_location:
            base["ssl.ca.location"] = cfg.kafka_ssl_ca_location
    if group_id:
        base["group.id"] = group_id
    return base


class KafkaService:
    """Kafka 诊断与受控生产。

    诊断读取一律使用独立临时组 + auto.commit/store=false，绝不动业务消费组 offset。
    """

    def __init__(self, cfg: Settings):
        self.cfg = cfg
        try:
            self._base = build_client_config(cfg)
            self._auth_error: str | None = None
        except RuntimeError as exc:
            # 配置缺失时保持客户端可构造：使用无认证的降级配置，使用时再抛可读错误
            self._auth_error = str(exc)
            self._base = {"bootstrap.servers": cfg.kafka_bootstrap_servers, "socket.timeout.ms": 5000}
        self.admin = AdminClient(self._base)
        self.producer = Producer(self._base)
        self._metadata_cache: dict[str, Any] = {"at": 0.0, "value": None}

    def _ready(self) -> None:
        if self._auth_error:
            raise RuntimeError(self._auth_error)

    def _consumer(self, group_id: str, **extra: Any) -> Consumer:
        config = {
            **self._base,
            "session.timeout.ms": 6000,   # 消费端专有属性
            **extra,
            "group.id": group_id,
            "enable.auto.commit": False,
        }
        return Consumer(config)

    # ---------- 元数据（带短 TTL 缓存） ----------

    async def metadata(self, force: bool = False) -> dict[str, Any]:
        if not force and self._metadata_cache["value"] is not None:
            age = time.monotonic() - self._metadata_cache["at"]
            if age < self.cfg.kafka_metadata_cache_seconds:
                return self._metadata_cache["value"]
        value = await asyncio.to_thread(self._metadata)
        self._metadata_cache = {"at": time.monotonic(), "value": value}
        return value

    def _metadata(self) -> dict[str, Any]:
        self._ready()
        md = self.admin.list_topics(timeout=5)
        brokers = [{"id": b.id, "host": b.host, "port": b.port} for b in md.brokers.values()]
        topics = []
        consumer = self._consumer("healthmind-control-metadata")
        try:
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
        finally:
            consumer.close()
        return {"brokers": brokers, "topics": topics}

    # ---------- 消费组（offset 明细 + 成员 + lag） ----------

    async def groups(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._groups)

    def _groups(self) -> list[dict[str, Any]]:
        self._ready()
        result = self.admin.list_consumer_groups(request_timeout=5).result(6)
        groups: list[dict[str, Any]] = []
        for listing in result.valid:
            if listing.group_id.startswith(SELF_GROUP_PREFIX):
                continue  # 不展示控制台自身的诊断组
            item: dict[str, Any] = {
                "group_id": listing.group_id,
                "state": str(listing.state),
                "simple": listing.is_simple_consumer_group,
                "members": [], "offsets": [], "lag": 0,
            }
            try:
                offsets = self.admin.list_consumer_group_offsets(
                    [ConsumerGroupTopicPartitions(listing.group_id)], request_timeout=5,
                )[listing.group_id].result(6)
                md = self.admin.list_topics(timeout=5)
                detail = []
                for tp in sorted(offsets.topic_partitions, key=lambda x: (x.topic, x.partition)):
                    if tp.offset < 0 or tp.topic not in md.topics:
                        continue
                    try:
                        _, high = self._watermark(tp.topic, tp.partition)
                    except Exception:
                        high = None
                    lag = max(0, high - tp.offset) if high is not None else None
                    detail.append({"topic": tp.topic, "partition": tp.partition, "offset": tp.offset, "high": high, "lag": lag})
                    item["lag"] += lag or 0
                item["offsets"] = detail
            except Exception:
                pass
            try:
                item["members"] = self._group_members(listing.group_id)
            except Exception:
                pass
            groups.append(item)
        return groups

    def _watermark(self, topic: str, partition: int) -> tuple[Any, Any]:
        consumer = self._consumer("healthmind-control-watermark")
        try:
            return consumer.get_watermark_offsets(TopicPartition(topic, partition), timeout=3)
        finally:
            consumer.close()

    def _group_members(self, group_id: str) -> list[dict[str, Any]]:
        description = self.admin.describe_consumer_groups([group_id], request_timeout=5)[group_id].result(6)
        members = []
        for member in description.members:
            assignments = []
            for tp in member.assignment or []:
                assignments.append({"topic": tp.topic, "partition": tp.partition})
            members.append({
                "member_id": member.member_id,
                "client_id": member.client_id,
                "host": member.host,
                "assignments": assignments,
            })
        return members

    # ---------- 消息查看（只读，含过滤与按时间/offset 起读） ----------

    async def messages(self, topic: str, partition: int = 0, start: str = "latest",
                       offset: int | None = None, time_ms: int | None = None,
                       limit: int = 50, key: str | None = None, event_id: str | None = None,
                       trace_id: str | None = None, event_type: str | None = None,
                       contains: str | None = None, max_scan: int | None = None) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._messages, topic, partition, start, offset, time_ms, min(limit, 100),
            key, event_id, trace_id, event_type, contains, max_scan,
        )

    def _messages(self, topic: str, partition: int, start: str, offset: int | None,
                  time_ms: int | None, limit: int, key: str | None, event_id: str | None,
                  trace_id: str | None, event_type: str | None, contains: str | None,
                  max_scan: int | None) -> list[dict[str, Any]]:
        self._ready()
        scan_budget = min(max_scan or self.cfg.kafka_max_scan_messages, self.cfg.kafka_max_scan_messages)
        consumer = self._consumer(
            f"healthmind-control-diagnostic-{datetime.now().timestamp()}",
            enable_auto_offset_store=False, auto_offset_reset="earliest",
        )
        try:
            tp = TopicPartition(topic, partition)
            low, high = consumer.get_watermark_offsets(tp, timeout=5)
            if offset is not None:
                target = offset
            elif start == "time" and time_ms:
                target = self._offset_for_time(consumer, tp, time_ms)
            elif start == "earliest":
                target = low
            else:
                target = max(low, (high or low) - limit * 3)
            consumer.assign([TopicPartition(topic, partition, target)])
            output = []
            scanned = 0
            empty = 0
            while len(output) < limit and empty < 3 and scanned < scan_budget:
                msg = consumer.poll(1)
                if msg is None:
                    empty += 1
                    continue
                if msg.error():
                    if msg.error().code() == -191:
                        break
                    raise KafkaException(msg.error())
                scanned += 1
                raw = msg.value().decode("utf-8", "replace") if msg.value() else ""
                msg_key = (msg.key() or b"").decode("utf-8", "replace")
                try:
                    payload: Any = json.loads(raw)
                except json.JSONDecodeError:
                    payload = raw
                if not self._match(payload, msg_key, key, event_id, trace_id, event_type, contains, raw):
                    continue
                output.append({
                    "topic": msg.topic(), "partition": msg.partition(), "offset": msg.offset(),
                    "timestamp": msg.timestamp()[1],
                    "key": msg_key,
                    "headers": dict(msg.headers() or []), "payload": payload,
                })
            if scanned >= scan_budget:
                output.append({"truncated_by_scan": True, "scanned": scanned})
            return output
        finally:
            consumer.close()

    @staticmethod
    def _offset_for_time(consumer: Consumer, tp: TopicPartition, time_ms: int) -> int:
        result = consumer.offsets_for_times([TopicPartition(tp.topic, tp.partition, time_ms)], timeout=5)
        found = result[0]
        if found is None or found.offset is None or found.offset < 0:
            raise KafkaException("时间点早于最早消息或分区无消息")
        return found.offset

    @staticmethod
    def _fields_of(payload: Any) -> dict[str, str]:
        """从消息对象提取 event 字段（兼容顶层或 payload 内嵌两种结构）。"""
        fields: dict[str, str] = {}
        if not isinstance(payload, dict):
            return fields
        for name in ("event_id", "event_type", "trace_id"):
            value = payload.get(name)
            if isinstance(value, str):
                fields[name] = value
        inner = payload.get("payload")
        if isinstance(inner, dict):
            for name in ("event_id", "event_type", "trace_id"):
                value = inner.get(name)
                if isinstance(value, str) and name not in fields:
                    fields[name] = value
        return fields

    def _match(self, payload: Any, msg_key: str, key: str | None, event_id: str | None,
               trace_id: str | None, event_type: str | None, contains: str | None, raw: str) -> bool:
        if key is not None and msg_key != key:
            return False
        fields = self._fields_of(payload)
        if event_id is not None and fields.get("event_id") != event_id:
            return False
        if trace_id is not None and fields.get("trace_id") != trace_id:
            return False
        if event_type is not None and fields.get("event_type") != event_type:
            return False
        if contains is not None and contains not in raw and contains not in msg_key:
            return False
        return True

    # ---------- 业务事件校验与受控生产 ----------

    def validate_event(self, topic: str, payload: Any) -> list[str]:
        warnings: list[str] = []
        if not isinstance(payload, dict):
            # 非业务 topic 允许纯文本/标量消息；业务 topic 必须是对象
            if topic in BUSINESS_TOPICS:
                warnings.append("业务 topic 的 payload 应为 JSON 对象（当前为非对象）")
            return warnings
        envelope_required = {"event_id", "event_type", "producer", "trace_id", "schema_version", "payload"}
        if topic in BUSINESS_TOPICS:
            missing = sorted(envelope_required - payload.keys())
            if missing:
                warnings.append("缺少业务事件字段: " + ", ".join(missing))
            expected_type = BUSINESS_TOPICS[topic]
            if payload.get("event_type") and payload.get("event_type") != expected_type:
                warnings.append(f"event_type 与 topic 不匹配：期望 {expected_type}")
            if payload.get("schema_version") and payload.get("schema_version") != "1.0":
                warnings.append("schema_version 应为 1.0")
        elif "event_id" not in payload and "event_type" not in payload:
            warnings.append("非标准消息：未包含 event_id/event_type 事件结构（可强制发送）")
        return warnings

    async def produce(self, topic: str, key: str | None, payload: Any,
                      headers: dict[str, str], partition: int | None) -> dict[str, Any]:
        return await asyncio.to_thread(self._produce, topic, key, payload, headers, partition)

    def _produce(self, topic: str, key: str | None, payload: Any,
                 headers: dict[str, str], partition: int | None) -> dict[str, Any]:
        self._ready()
        delivered: dict[str, Any] = {}
        def callback(error, message):
            if error:
                delivered["error"] = str(error)
            else:
                delivered.update(topic=message.topic(), partition=message.partition(), offset=message.offset())
        kwargs = {"topic": topic, "key": key, "value": json.dumps(payload, ensure_ascii=False),
                  "headers": list(headers.items()), "callback": callback}
        if partition is not None:
            kwargs["partition"] = partition
        self.producer.produce(**kwargs)
        remaining = self.producer.flush(10)
        if remaining or delivered.get("error"):
            raise RuntimeError(delivered.get("error") or f"{remaining} message(s) undelivered")
        return {"delivery": "ok", **delivered}
