import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from healthmind_control.config import Settings
from healthmind_control.services.dify import DifyService, _safe_cli_error


WORKSPACE_PAYLOAD = {
    "workspaces": [
        {"id": "workspace-old", "name": "Old", "current": False},
        {"id": "workspace-current", "name": "Current", "current": True},
    ]
}
APPS_PAYLOAD = {
    "data": [
        {"id": "app-workflow", "name": "Diet", "mode": "workflow"},
        {"id": "app-chat", "name": "Chat", "mode": "advanced-chat"},
    ]
}
APP_PAYLOAD = {
    "info": {"id": "app-workflow", "name": "Diet", "mode": "workflow"},
    "input_schema": {
        "type": "object",
        "properties": {"inputs": {"type": "object", "properties": {"task_id": {"type": "string"}}}},
    },
}


def make_service() -> DifyService:
    return DifyService(SimpleNamespace(difyctl_path="difyctl"))


@pytest.mark.asyncio
async def test_discover_uses_difyctl_oauth_and_normalizes_real_shapes(monkeypatch):
    service = make_service()
    calls: list[list[str]] = []
    payloads = {
        ("version", "-o", "json"): {
            "server": {"version": "1.17.1"},
            "compat": {"status": "too_new", "detail": "server is newer than tested maximum"},
        },
        ("auth", "whoami", "--json"): {"id": "account", "email": "user@example.com"},
        ("get", "workspace", "-o", "json"): WORKSPACE_PAYLOAD,
        ("get", "app", "-o", "json"): APPS_PAYLOAD,
        ("describe", "app", "app-workflow", "-o", "json", "--refresh"): APP_PAYLOAD,
    }

    async def fake_run(args, timeout=20):
        calls.append(args)
        if args[:2] == ["export", "studio-app"]:
            return 0, "kind: app\nworkflow: {}\n"
        return 0, json.dumps(payloads[tuple(args)])

    monkeypatch.setattr(service, "_run_difyctl", fake_run)
    try:
        result = await service.discover("app-workflow", with_dsl=True)
    finally:
        await service.close()

    assert result["authenticated"] is True
    assert result["workspace"]["id"] == "workspace-current"
    assert result["apps"] == APPS_PAYLOAD["data"]
    assert result["resolved"] == {
        "workspace_id": "workspace-current",
        "app_id": "app-workflow",
        "dify_input_schema": APP_PAYLOAD["input_schema"],
    }
    assert result["compatibility_warning"] == "server is newer than tested maximum"
    assert result["dsl"]["yaml"].startswith("kind: app")
    export_call = next(call for call in calls if call[:2] == ["export", "studio-app"])
    assert export_call == ["export", "studio-app", "app-workflow"]
    assert "--include-secret" not in export_call


@pytest.mark.asyncio
async def test_discover_stops_at_auth_failure_and_explains_login(monkeypatch):
    service = make_service()

    async def fake_run(args, timeout=20):
        if args[0] == "version":
            return 0, json.dumps({"compat": {"status": "compatible"}})
        return 4, "not logged in"

    monkeypatch.setattr(service, "_run_difyctl", fake_run)
    try:
        result = await service.discover()
    finally:
        await service.close()

    assert result["authenticated"] is False
    assert result["login_hint"] == "请先在终端运行 difyctl auth login"
    assert result["errors"]["auth"] == "not logged in"
    assert result["apps"] == []


def test_console_token_was_removed_and_frontend_uses_cli_only():
    settings = Settings(_env_file=None)
    assert not hasattr(settings, "dify_console_token")

    root = Path(__file__).parents[1]
    service = (root / "src/healthmind_control/services/dify.py").read_text(encoding="utf-8")
    api = (root / "src/healthmind_control/api/releases.py").read_text(encoding="utf-8")
    html = (root / "src/healthmind_control/templates/views/releases.html").read_text(encoding="utf-8")
    js = (root / "src/healthmind_control/static/js/views/releases.js").read_text(encoding="utf-8")
    combined = "\n".join((service, api, html, js))

    assert "HMC_DIFY_CONSOLE_TOKEN" not in combined
    assert "/api/dify/published" not in combined
    assert "w-console" not in combined
    assert "loadDifyctlApps(true)" in js
    assert "Dify 的运行输入 Schema 与 HealthMind 的 Kafka 事件契约不同" in js


def test_cli_error_redacts_oauth_credentials():
    message = "Authorization: Bearer top-secret dfoa_abc.DEF-123"
    safe = _safe_cli_error(message)
    assert "top-secret" not in safe
    assert "dfoa_" not in safe
    assert "Bearer ***" in safe
