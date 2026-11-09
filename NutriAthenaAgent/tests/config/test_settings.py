import os

import pytest

from nutriathena_agent.config import loader


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith(("NUTRIATHENA_", "AGENTDEVELOP_")):
            monkeypatch.delenv(name)
    monkeypatch.setattr(loader, "load_env", lambda: None)


def meal_environment(monkeypatch):
    values = {
        "MEAL_MODEL_ID": "vision-test",
        "MODEL_API_KEY": "unit-test-key",
        "MODEL_BASE_URL": "https://model.example.invalid/v1",
        "MCP_URL": "https://mcp.example.invalid",
        "MCP_OAUTH_TOKEN_URL": "https://issuer.example.invalid/token",
        "MCP_CLIENT_ID": "test-client",
        "MCP_CLIENT_SECRET": "unit-test-secret",
    }
    for suffix, value in values.items():
        monkeypatch.setenv("NUTRIATHENA_" + suffix, value)


def runtime_environment(monkeypatch):
    for suffix, value in {
        "DATABASE_URL": "postgresql://test-only",
        "OAUTH_ISSUER": "https://issuer.example.invalid",
        "OAUTH_JWKS_URL": "https://issuer.example.invalid/jwks",
        "RELEASE_ID": "33333333-3333-4333-8333-333333333333",
        "DEPLOYMENT_KEY": "test-deployment",
        "ASSISTANT_ID": "test-assistant",
    }.items():
        monkeypatch.setenv("NUTRIATHENA_" + suffix, value)


def test_new_alias_wins_and_empty_new_value_falls_back(monkeypatch):
    meal_environment(monkeypatch)
    monkeypatch.setenv("AGENTDEVELOP_MEAL_MODEL", "legacy-vision")
    assert loader.load_meal_settings().model == "vision-test"
    monkeypatch.setenv("NUTRIATHENA_MEAL_MODEL_ID", "")
    assert loader.load_meal_settings().model == "legacy-vision"


def test_csv_hosts_debug_alias_and_secret_repr(monkeypatch):
    meal_environment(monkeypatch)
    monkeypatch.setenv("NUTRIATHENA_MEDIA_ALLOWED_HOSTS", " Media.Example.Test, *.example.test, ,*")
    monkeypatch.setenv("NUTRIATHENA_DEBUG", "yes")
    settings = loader.load_meal_settings()
    assert settings.media_allowed_hosts == {"media.example.test", "*.example.test", "*"}
    assert settings.debug_level.value == "trace"
    assert "unit-test-key" not in repr(settings)
    assert "unit-test-secret" not in repr(settings)


@pytest.mark.parametrize("suffix,value", [
    ("PORT", "0"), ("LEASE_SECONDS", "3"), ("RUN_TIMEOUT_SECONDS", "0.05"),
    ("WORKER_POLL_SECONDS", "nan"), ("RESULT_RETENTION_HOURS", "23"),
    ("ROW_RETENTION_DAYS", "179"), ("RELEASE_ID", "invalid"),
])
def test_environment_limits_are_enforced_without_leaking_values(monkeypatch, suffix, value):
    runtime_environment(monkeypatch)
    monkeypatch.setenv("NUTRIATHENA_" + suffix, value)
    with pytest.raises(RuntimeError) as error:
        loader.load_runtime_settings()
    assert "postgresql://test-only" not in str(error.value)


def test_model_example_configuration_does_not_require_runtime_configuration(monkeypatch):
    monkeypatch.setenv("AGENTDEVELOP_API_KEY", "unit-test-key")
    monkeypatch.setenv("AGENTDEVELOP_BASE_URL", "https://model.example.invalid/v1")
    assert loader.load_model_settings().model == "deepseek-chat"


def test_injected_short_timeouts_remain_usable_for_isolated_worker_tests(monkeypatch):
    runtime_environment(monkeypatch)
    settings = loader.load_runtime_settings().model_copy(update={"lease_seconds": 3, "run_timeout_seconds": 0.05})
    assert settings.lease_seconds == 3
    assert settings.run_timeout_seconds == 0.05
