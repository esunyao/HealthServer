from __future__ import annotations

from types import SimpleNamespace

import pytest

from nutriathena_agent import config
from nutriathena_agent.integrations import model


def test_build_model_loads_public_settings_lazily_and_assembles_only_configured_values(monkeypatch):
    settings = SimpleNamespace(
        model="teaching-model",
        base_url="https://models.example.test/v1",
        api_key="synthetic-key",
    )
    calls = []
    client = object()

    def load_settings():
        calls.append("settings")
        return settings

    def create_model(**kwargs):
        calls.append(kwargs)
        return client

    monkeypatch.setattr(config, "load_model_settings", load_settings)
    monkeypatch.setattr(model, "ChatOpenAI", create_model)
    assert calls == []
    assert model.build_model() is client
    assert calls == [
        "settings",
        {"model": settings.model, "base_url": settings.base_url, "api_key": settings.api_key},
    ]


def test_build_model_preserves_configuration_failure_without_constructing_a_client(monkeypatch):
    error = ValueError("Missing configured model")

    def load_settings():
        raise error

    def unexpected_constructor(**kwargs):
        pytest.fail("No client may be constructed after settings fail")

    monkeypatch.setattr(config, "load_model_settings", load_settings)
    monkeypatch.setattr(model, "ChatOpenAI", unexpected_constructor)
    with pytest.raises(ValueError) as caught:
        model.build_model()
    assert caught.value is error


def test_build_meal_model_preserves_temperature_timeout_and_retries(monkeypatch):
    settings = config.MealSettings(
        model="configured-vision-model",
        base_url="https://models.example.test/v1",
        api_key="synthetic-key",
        mcp_url="https://healthmind.example.test/mcp",
        token_url="https://issuer.example.test/token",
        oauth_client_id="synthetic-client",
        oauth_client_secret="synthetic-secret",
        mcp_scopes="context.read",
    )
    calls = []
    client = object()

    def create_model(**kwargs):
        calls.append(kwargs)
        return client

    monkeypatch.setattr(model, "ChatOpenAI", create_model)
    assert model.build_meal_model(settings) is client
    assert calls == [{
        "model": settings.model,
        "base_url": settings.base_url,
        "api_key": settings.api_key,
        "temperature": 0,
        "timeout": 180,
        "max_retries": 1,
    }]
