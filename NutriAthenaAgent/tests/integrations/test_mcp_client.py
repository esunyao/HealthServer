from __future__ import annotations

import asyncio
import io
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import mcp
import mcp.client.streamable_http as streamable_http
import pytest
from mcp.types import CallToolResult, TextContent

from nutriathena_agent.config import MealSettings
from nutriathena_agent.integrations.mcp import (
    CAPTURE_CONTEXT_TOOL,
    NUTRITION_CONTEXT_TOOL,
    McpSetupError,
    _stable_tool_call_id,
    connect_healthmind_mcp,
)
from nutriathena_agent.integrations.mcp import client as mcp_client
from nutriathena_agent.observability import DebugLevel, configure_logging, log_exception
from ._fakes import ATTEMPT_ID, TASK_ID, capture_payload


@pytest.fixture
def settings():
    return MealSettings(
        model="offline-model",
        api_key="synthetic-key",
        base_url="https://models.example.test/v1",
        mcp_url="https://healthmind.example.test/mcp",
        token_url="https://issuer.example.test/token",
        oauth_client_id="synthetic-client",
        oauth_client_secret="synthetic-secret",
        mcp_scopes="capture.read nutrition.read",
    )


def install_oauth_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    clients = []

    def create_client(**kwargs):
        clients.append(kwargs)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(mcp_client.httpx, "AsyncClient", create_client)
    return clients


@pytest.fixture
def sdk(monkeypatch):
    state = SimpleNamespace(
        events=[],
        calls=[],
        stream_options=[],
        failure=OSError("offline SDK failure"),
        fail_stage=None,
        cleanup_failure=None,
        names=[CAPTURE_CONTEXT_TOOL, NUTRITION_CONTEXT_TOOL],
        capture_result=CallToolResult(
            content=[TextContent(type="text", text=json.dumps(capture_payload(notes="米饭约半碗")))],
        ),
        nutrition_result=CallToolResult(content=[], structuredContent={"age_years": 18}),
    )

    class Session:
        def __init__(self, read, write):
            assert (read, write) == ("offline-read", "offline-write")

        async def __aenter__(self):
            state.events.append("session.open")
            return self

        async def __aexit__(self, *exc):
            state.events.append("session.close")
            if state.cleanup_failure is not None:
                raise state.cleanup_failure

        async def initialize(self):
            state.events.append("initialize")
            if state.fail_stage == "initialize":
                raise state.failure

        async def list_tools(self):
            state.events.append("list_tools")
            if state.fail_stage == "list_tools":
                raise state.failure
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in state.names])

        async def call_tool(self, name, *, arguments, meta):
            state.calls.append((name, arguments, meta))
            if state.fail_stage == "capture_prefetch":
                raise state.failure
            if name == CAPTURE_CONTEXT_TOOL:
                return state.capture_result
            if name == NUTRITION_CONTEXT_TOOL:
                return state.nutrition_result
            pytest.fail("Unexpected MCP tool")

    @asynccontextmanager
    async def open_stream(url, **kwargs):
        state.stream_options.append((url, kwargs))
        state.events.append("stream.open")
        if state.fail_stage == "connect":
            raise state.failure
        try:
            yield "offline-read", "offline-write", lambda: None
        finally:
            state.events.append("stream.close")

    monkeypatch.setattr(mcp, "ClientSession", Session)
    monkeypatch.setattr(streamable_http, "streamablehttp_client", open_stream)
    return state


def test_sdk_lifecycle_prefetches_capture_once_and_defers_nutrition(monkeypatch, settings, sdk):
    oauth_requests = []

    def oauth_response(request):
        oauth_requests.append(request)
        return httpx.Response(200, json={"access_token": "synthetic-access-token"})

    clients = install_oauth_transport(monkeypatch, oauth_response)

    async def invoke():
        bindings = await connect_healthmind_mcp(settings, task_id=TASK_ID, attempt_id=ATTEMPT_ID)
        assert bindings.called == {"capture_context"}
        assert bindings.presented == set()
        assert [item[0] for item in sdk.calls] == [CAPTURE_CONTEXT_TOOL]
        assert bindings.capture_payload["notes"] == "米饭约半碗"
        assert bindings.capture_payload["image_urls"][0]["url"] == "https://media.example.test/signed"
        safe_capture = json.loads(await bindings.tools[0].ainvoke({}))
        assert safe_capture["notes"] == "米饭约半碗"
        assert safe_capture["confirmed_image_count"] == 1
        assert "image_urls" not in safe_capture
        assert "capture_session_id" not in safe_capture
        assert len(sdk.calls) == 1
        assert bindings.presented == {"capture_context"}
        assert json.loads(await bindings.tools[1].ainvoke({})) == {"age_years": 18}
        assert bindings.called == bindings.presented == {"capture_context", "nutrition_context"}
        with pytest.raises(RuntimeError, match="only once"):
            await bindings.tools[0].ainvoke({})
        with pytest.raises(RuntimeError, match="only once"):
            await bindings.tools[1].ainvoke({})
        await bindings.aclose()
        await bindings.aclose()

    asyncio.run(invoke())
    assert sdk.calls == [
        (
            name,
            {"taskId": TASK_ID, "attemptId": ATTEMPT_ID},
            {"tool_call_id": _stable_tool_call_id(ATTEMPT_ID, name)},
        )
        for name in (CAPTURE_CONTEXT_TOOL, NUTRITION_CONTEXT_TOOL)
    ]
    assert sdk.events == ["stream.open", "session.open", "initialize", "list_tools", "session.close", "stream.close"]
    assert sdk.stream_options == [(settings.mcp_url, {
        "headers": {"Authorization": "Bearer synthetic-access-token"},
        "timeout": 20,
        "sse_read_timeout": 20,
    })]
    assert clients == [{"timeout": 15, "follow_redirects": False}]
    assert len(oauth_requests) == 1
    assert parse_qs(oauth_requests[0].content.decode()) == {
        "grant_type": ["client_credentials"],
        "client_id": [settings.oauth_client_id],
        "client_secret": [settings.oauth_client_secret],
        "scope": [settings.mcp_scopes],
    }


@pytest.mark.parametrize("stage", ["connect", "initialize", "list_tools", "capture_prefetch", "bind_tools"])
def test_connection_failure_keeps_stage_and_root_cause_and_closes_resources(monkeypatch, settings, sdk, stage):
    install_oauth_transport(monkeypatch, lambda request: httpx.Response(200, json={"access_token": "synthetic-token"}))
    sdk.fail_stage = stage
    if stage == "bind_tools":
        def fail_bind(*args, **kwargs):
            raise sdk.failure

        monkeypatch.setattr(mcp_client, "bind_context_tools", fail_bind)
    with pytest.raises(McpSetupError) as caught:
        asyncio.run(connect_healthmind_mcp(settings, task_id=TASK_ID, attempt_id=ATTEMPT_ID))
    assert caught.value.stage == stage
    assert caught.value.__cause__ is sdk.failure
    if stage != "connect":
        assert sdk.events[-2:] == ["session.close", "stream.close"]
    assert all(call[0] != NUTRITION_CONTEXT_TOOL for call in sdk.calls)


def test_missing_required_tool_fails_before_capture_prefetch(monkeypatch, settings, sdk):
    install_oauth_transport(monkeypatch, lambda request: httpx.Response(200, json={"access_token": "synthetic-token"}))
    sdk.names = [CAPTURE_CONTEXT_TOOL]
    with pytest.raises(McpSetupError) as caught:
        asyncio.run(connect_healthmind_mcp(settings, task_id=TASK_ID, attempt_id=ATTEMPT_ID))
    assert caught.value.stage == "list_tools"
    assert sdk.calls == []
    assert sdk.events[-2:] == ["session.close", "stream.close"]


def test_prefetch_error_result_never_exposes_bindings_or_calls_nutrition(monkeypatch, settings, sdk):
    install_oauth_transport(monkeypatch, lambda request: httpx.Response(200, json={"access_token": "synthetic-token"}))
    sdk.capture_result = CallToolResult(content=[], structuredContent=capture_payload(), isError=True)
    with pytest.raises(McpSetupError, match="tool returned an error") as caught:
        asyncio.run(connect_healthmind_mcp(settings, task_id=TASK_ID, attempt_id=ATTEMPT_ID))
    assert caught.value.stage == "parse_context"
    assert len(sdk.calls) == 1
    assert sdk.calls[0][0] == CAPTURE_CONTEXT_TOOL
    assert sdk.events[-2:] == ["session.close", "stream.close"]


def test_cleanup_failure_does_not_replace_original_failure(monkeypatch, settings, sdk):
    install_oauth_transport(monkeypatch, lambda request: httpx.Response(200, json={"access_token": "synthetic-token"}))
    sdk.fail_stage = "initialize"
    sdk.cleanup_failure = OSError("offline cleanup failure")
    with pytest.raises(McpSetupError) as caught:
        asyncio.run(connect_healthmind_mcp(settings, task_id=TASK_ID, attempt_id=ATTEMPT_ID))
    assert caught.value.stage == "initialize"
    assert caught.value.__cause__ is sdk.failure
    assert "MCP cleanup failed: OSError" in sdk.failure.__notes__
    assert sdk.events[-2:] == ["session.close", "stream.close"]


def test_cancellation_is_propagated_after_cleanup(monkeypatch, settings, sdk):
    install_oauth_transport(monkeypatch, lambda request: httpx.Response(200, json={"access_token": "synthetic-token"}))
    sdk.fail_stage = "initialize"
    sdk.failure = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError) as caught:
        asyncio.run(connect_healthmind_mcp(settings, task_id=TASK_ID, attempt_id=ATTEMPT_ID))
    assert caught.value is sdk.failure
    assert sdk.events[-2:] == ["session.close", "stream.close"]


@pytest.mark.parametrize("status", [302, 400, 401, 503])
def test_oauth_errors_keep_status_and_safe_server_notes_without_following_redirects(monkeypatch, settings, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={"location": "https://other.example.test/token"}, json={
            "error": "invalid_client", "error_description": "synthetic client denied",
        })

    install_oauth_transport(monkeypatch, handler)
    with pytest.raises(McpSetupError, match=f"HTTP {status}") as caught:
        asyncio.run(mcp_client._access_token(settings))
    assert caught.value.stage == "oauth"
    assert "oauth_error=invalid_client" in caught.value.__notes__
    assert "oauth_error_description=synthetic client denied" in caught.value.__notes__
    assert len(requests) == 1


@pytest.mark.parametrize(
    "response,message",
    [
        (httpx.Response(200, text="invalid"), "invalid JSON"),
        (httpx.Response(200, json=[]), "invalid JSON"),
        (httpx.Response(200, json={}), "access_token"),
        (httpx.Response(200, json={"access_token": ""}), "access_token"),
        (httpx.Response(200, json={"access_token": 12}), "access_token"),
    ],
)
def test_oauth_rejects_invalid_json_or_missing_token(monkeypatch, settings, response, message):
    install_oauth_transport(monkeypatch, lambda request: response)
    with pytest.raises(McpSetupError, match=message) as caught:
        asyncio.run(mcp_client._access_token(settings))
    assert caught.value.stage == "oauth"


def test_oauth_failure_log_preserves_cause_and_redacts_url(monkeypatch, settings):
    stream = io.StringIO()
    configure_logging(DebugLevel.TRACE, sink=stream, level="DEBUG", file_path=None, color="never", force=True)
    root_cause = httpx.ConnectError("offline connect https://issuer.example.test/token?token=never-log")

    def handler(request):
        raise root_cause

    install_oauth_transport(monkeypatch, handler)
    with pytest.raises(McpSetupError) as caught:
        asyncio.run(connect_healthmind_mcp(settings, task_id=TASK_ID, attempt_id=ATTEMPT_ID))
    assert caught.value.stage == "oauth"
    assert caught.value.__cause__ is root_cause
    log_exception("mcp.connect.failed", caught.value, stage=caught.value.stage)
    output = stream.getvalue()
    assert "McpSetupError" in output
    assert "ConnectError" in output
    assert "direct cause" in output
    assert 'stage="oauth"' in output
    assert "https://issuer.example.test" not in output
    assert "never-log" not in output
