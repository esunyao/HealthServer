import os

import pytest

from nutriathena_agent.config import loader


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith("NUTRIATHENA_") and name != "NUTRIATHENA_SKIP_LOCAL_CONFIG":
            monkeypatch.delenv(name)


@pytest.fixture
def local_config(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.setattr(loader, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(loader, "CONFIG_FILE", tmp_path / "config.yaml")
    monkeypatch.delenv("NUTRIATHENA_SKIP_LOCAL_CONFIG")
    return loader.ENV_FILE, loader.CONFIG_FILE


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


@pytest.mark.parametrize(
    "shell,dotenv,expected",
    [("shell", "dotenv", "shell"), (None, "dotenv", "dotenv"), (None, "", "yaml")],
)
def test_local_config_precedence(local_config, monkeypatch, shell, dotenv, expected):
    env_file, yaml_file = local_config
    env_file.write_text(f"NUTRIATHENA_MODEL_ID={dotenv}\n", encoding="utf-8")
    yaml_file.write_text("model: {id: yaml}\n", encoding="utf-8")
    if shell is not None:
        monkeypatch.setenv(loader.MODEL_VAR, shell)
    loader.load_env()
    assert os.environ[loader.MODEL_VAR] == expected


def test_yaml_mapping_and_literal_dotenv_values(local_config, monkeypatch):
    meal_environment(monkeypatch)
    monkeypatch.delenv(loader.API_KEY_VAR)
    env_file, yaml_file = local_config
    env_file.write_text(
        "\n# NUTRIATHENA_DEBUG=full\nNUTRIATHENA_MODEL_API_KEY='test=${literal}'\n"
        'NUTRIATHENA_MCP_SCOPES=""\nUNRELATED_CONFIG=ignored\n',
        encoding="utf-8",
    )
    yaml_file.write_text(
        "model: {api_key: null}\nmcp: {scopes: yaml.scope}\n"
        'media: {allowed_hosts: [media.example.test, "*.example.test"]}\n'
        "debug: off\nlog: {file: ''}\n",
        encoding="utf-8",
    )
    settings = loader.load_meal_settings()
    assert settings.api_key == "test=${literal}"
    assert settings.mcp_scopes == "yaml.scope"
    assert settings.media_allowed_hosts == {"media.example.test", "*.example.test"}
    assert settings.debug_level.value == "off"
    assert "NUTRIATHENA_LOG_FILE" not in os.environ
    assert "UNRELATED_CONFIG" not in os.environ


@pytest.mark.parametrize(
    "content, message",
    [("model: {api_key: '\nprivate-test-key", "格式错误"), ("[]", "键值映射")],
)
def test_invalid_yaml_does_not_disclose_input(local_config, content, message):
    _, yaml_file = local_config
    yaml_file.write_text(content, encoding="utf-8")
    with pytest.raises(RuntimeError, match=message) as error:
        loader.load_env()
    assert "private-test-key" not in str(error.value)
    assert error.value.__cause__ is None


def test_skip_local_config_ignores_both_files(local_config, monkeypatch):
    env_file, yaml_file = local_config
    env_file.write_text("NUTRIATHENA_MODEL_ID=dotenv\n", encoding="utf-8")
    yaml_file.write_text("not: [valid", encoding="utf-8")
    monkeypatch.setenv("NUTRIATHENA_SKIP_LOCAL_CONFIG", "1")
    loader.load_env()
    assert loader.MODEL_VAR not in os.environ


def test_csv_hosts_debug_alias_and_secret_repr(monkeypatch):
    meal_environment(monkeypatch)
    monkeypatch.setenv(
        "NUTRIATHENA_MEDIA_ALLOWED_HOSTS", " Media.Example.Test, *.example.test, ,*"
    )
    monkeypatch.setenv("NUTRIATHENA_DEBUG", "yes")
    settings = loader.load_meal_settings()
    assert settings.media_allowed_hosts == {"media.example.test", "*.example.test", "*"}
    assert settings.debug_level.value == "trace"
    assert "unit-test-key" not in repr(settings)
    assert "unit-test-secret" not in repr(settings)


@pytest.mark.parametrize(
    "suffix,value",
    [
        ("PORT", "0"),
        ("PORT", "8101.0"),
        ("LEASE_SECONDS", "3"),
        ("RUN_TIMEOUT_SECONDS", "0.05"),
        ("WORKER_POLL_SECONDS", "nan"),
        ("RESULT_RETENTION_HOURS", "23"),
        ("ROW_RETENTION_DAYS", "179"),
        ("RELEASE_ID", "invalid"),
    ],
)
def test_environment_limits_are_enforced_without_leaking_values(
    monkeypatch, suffix, value
):
    runtime_environment(monkeypatch)
    monkeypatch.setenv("NUTRIATHENA_" + suffix, value)
    with pytest.raises(RuntimeError) as error:
        loader.load_runtime_settings()
    assert "postgresql://test-only" not in str(error.value)


def test_model_example_configuration_does_not_require_runtime_configuration(
    monkeypatch,
):
    monkeypatch.setenv(loader.API_KEY_VAR, "unit-test-key")
    monkeypatch.setenv(loader.BASE_URL_VAR, "https://model.example.invalid/v1")
    monkeypatch.setenv("AGENTDEVELOP_MODEL", "legacy-model")
    assert loader.load_model_settings().model == "deepseek-chat"


def test_injected_short_timeouts_remain_usable_for_isolated_worker_tests(monkeypatch):
    runtime_environment(monkeypatch)
    settings = loader.load_runtime_settings().model_copy(
        update={"lease_seconds": 3, "run_timeout_seconds": 0.05}
    )
    assert settings.lease_seconds == 3
    assert settings.run_timeout_seconds == 0.05
