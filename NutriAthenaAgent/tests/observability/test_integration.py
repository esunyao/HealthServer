from __future__ import annotations

import asyncio
import importlib
import io
import os
from types import SimpleNamespace

import httpx
import pytest

from nutriathena_agent.config import load_meal_settings, load_runtime_settings
from nutriathena_agent.observability import DebugLevel
from .test_logging import _capture

_TASK_ID = "11111111-1111-4111-8111-111111111111"
_ATTEMPT_ID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def cli():
    return importlib.import_module("nutriathena_agent.cli.commands")


_RUNTIME_ENV = {
    "NUTRIATHENA_DATABASE_URL": "postgresql://unused",
    "NUTRIATHENA_OAUTH_ISSUER": "https://issuer.example.test/",
    "NUTRIATHENA_OAUTH_JWKS_URL": "https://issuer.example.test/jwks/",
    "NUTRIATHENA_RELEASE_ID": "33333333-3333-4333-8333-333333333333",
    "NUTRIATHENA_DEPLOYMENT_KEY": "meal-analysis-test",
    "NUTRIATHENA_ASSISTANT_ID": "nutriathena-meal-test",
}


_MEAL_ENV = {
    "NUTRIATHENA_MEAL_MODEL_ID": "vision-test",
    "NUTRIATHENA_MODEL_API_KEY": "test-key",
    "NUTRIATHENA_MODEL_BASE_URL": "https://example.invalid/v1",
    "NUTRIATHENA_MCP_URL": "https://mcp.example.invalid/mcp",
    "NUTRIATHENA_MCP_OAUTH_TOKEN_URL": "https://issuer.example.invalid/token",
    "NUTRIATHENA_MCP_CLIENT_ID": "test-client",
    "NUTRIATHENA_MCP_CLIENT_SECRET": "test-secret",
}


def test_runtime_settings_reads_debug_level(monkeypatch):
    for name, value in _RUNTIME_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("NUTRIATHENA_DEBUG", "full")

    assert load_runtime_settings().debug_level is DebugLevel.FULL



def test_meal_settings_default_and_override_debug_level(monkeypatch):
    for name, value in _MEAL_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("NUTRIATHENA_DEBUG", "off")
    assert load_meal_settings().debug_level is DebugLevel.OFF

    monkeypatch.setenv("NUTRIATHENA_DEBUG", "trace")
    assert load_meal_settings().debug_level is DebugLevel.TRACE



def _fake_meal(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_run(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr("nutriathena_agent.meal.runner.run_meal_analysis", fake_run)
    return captured



def test_meal_cli_debug_full_sets_environment(monkeypatch, cli):
    monkeypatch.delenv("NUTRIATHENA_DEBUG", raising=False)
    _fake_meal(monkeypatch)

    code = cli.main(["meal", "--debug", "full", "--task-id", _TASK_ID, "--attempt-id", _ATTEMPT_ID])

    assert code == 0
    assert os.environ["NUTRIATHENA_DEBUG"] == "full"



def test_meal_cli_debug_off_overrides_environment(monkeypatch, cli):
    monkeypatch.setenv("NUTRIATHENA_DEBUG", "trace")
    _fake_meal(monkeypatch)

    code = cli.main(["meal", "--debug", "off", "--task-id", _TASK_ID, "--attempt-id", _ATTEMPT_ID])

    assert code == 0
    assert os.environ["NUTRIATHENA_DEBUG"] == "off"



def test_meal_cli_without_debug_keeps_environment(monkeypatch, cli):
    monkeypatch.setenv("NUTRIATHENA_DEBUG", "trace")
    _fake_meal(monkeypatch)

    code = cli.main(["meal", "--task-id", _TASK_ID, "--attempt-id", _ATTEMPT_ID])

    assert code == 0
    assert os.environ["NUTRIATHENA_DEBUG"] == "trace"



def test_serve_cli_debug_argument_is_applied_from_parser(monkeypatch, cli):
    monkeypatch.delenv("NUTRIATHENA_DEBUG", raising=False)
    args = cli.build_parser().parse_args(["serve", "--debug", "trace"])

    cli._apply_debug_argument(SimpleNamespace(**vars(args)))

    assert os.environ["NUTRIATHENA_DEBUG"] == "trace"



def test_oauth_failure_logs_full_cause_chain_without_url(monkeypatch):
    from nutriathena_agent.integrations.mcp import McpSetupError, connect_healthmind_mcp
    from nutriathena_agent.observability import log_exception

    stream = _capture()
    settings = SimpleNamespace(
        token_url="https://issuer.test/token?token=never-log",
        oauth_client_id="client",
        oauth_client_secret="secret",
        mcp_scopes="scope.read",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "connect failed https://issuer.test/token?token=never-log",
            request=request,
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "nutriathena_agent.integrations.mcp.client.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    with pytest.raises(McpSetupError) as captured:
        asyncio.run(
            connect_healthmind_mcp(
                settings,
                task_id=_TASK_ID,
                attempt_id=_ATTEMPT_ID,
            )
        )

    log_exception(
        "mcp.connect.failed",
        captured.value,
        stage=getattr(captured.value, "stage", None),
    )
    output = stream.getvalue()
    assert "McpSetupError" in output
    assert "ConnectError" in output
    assert "direct cause" in output
    assert 'stage="oauth"' in output
    assert "https://issuer.test" not in output
    assert "issuer.test/token" not in output
    assert "never-log" not in output

