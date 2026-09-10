from types import SimpleNamespace

import pytest

from healthmind_control.services import kafka as kmod


def _fake_cfg(**overrides):
    defaults = dict(
        kafka_bootstrap_servers="kafka.local:9092",
        kafka_security_protocol="PLAINTEXT",
        kafka_sasl_mechanism=None,
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_ssl_ca_location=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_kafka_client_config_plaintext():
    cfg = _fake_cfg()
    conf = kmod.build_client_config(cfg, "group-1")
    assert conf["bootstrap.servers"] == "kafka.local:9092"
    assert conf["group.id"] == "group-1"
    assert "security.protocol" not in conf
    assert "sasl.username" not in conf


def test_kafka_consumer_only_properties_are_scoped():
    """session.timeout.ms 只给消费端：Producer/Admin 传入会触发 librdkafka CONFWARN。"""
    cfg = _fake_cfg()
    producer_conf = kmod.build_client_config(cfg)
    consumer_conf = kmod.build_client_config(cfg, "g", consumer=True)
    assert "session.timeout.ms" not in producer_conf
    assert consumer_conf["session.timeout.ms"] == 6000


def test_kafka_client_config_sasl_ssl():
    cfg = _fake_cfg(
        kafka_security_protocol="SASL_SSL",
        kafka_sasl_mechanism="SCRAM-SHA-256",
        kafka_sasl_username="ops",
        kafka_sasl_password="s3cret",
        kafka_ssl_ca_location="C:/certs/kafka-ca.pem",
    )
    conf = kmod.build_client_config(cfg)
    assert conf["security.protocol"] == "SASL_SSL"
    assert conf["sasl.mechanism"] == "SCRAM-SHA-256"
    assert conf["sasl.username"] == "ops"
    assert conf["sasl.password"] == "s3cret"
    assert conf["ssl.ca.location"] == "C:/certs/kafka-ca.pem"


def test_kafka_client_config_missing_sasl_creds_raises():
    cfg = _fake_cfg(kafka_security_protocol="SASL_PLAINTEXT", kafka_sasl_username=None)
    with pytest.raises(RuntimeError, match="SASL_USERNAME"):
        kmod.build_client_config(cfg)
