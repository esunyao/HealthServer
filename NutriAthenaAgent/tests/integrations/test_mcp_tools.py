from __future__ import annotations

import asyncio
import io
import json
from uuid import UUID, uuid5

import pytest
from langchain_core.messages import ToolMessage

from nutriathena_agent.integrations.mcp import (
    CAPTURE_CONTEXT_TOOL,
    NUTRITION_CONTEXT_TOOL,
    McpSetupError,
    _McpSdkRemoteTool,
    bind_context_tools,
    _stable_tool_call_id,
)
from nutriathena_agent.logging_service import DebugLevel, configure_logging
from ._fakes import ATTEMPT_ID, TASK_ID, FakeMcpTool, capture_context_payload


def test_stable_tool_ids_use_full_tool_codes_and_attempt_namespace():
    capture_id = _stable_tool_call_id(ATTEMPT_ID, CAPTURE_CONTEXT_TOOL)
    nutrition_id = _stable_tool_call_id(ATTEMPT_ID, NUTRITION_CONTEXT_TOOL)
    assert capture_id == str(uuid5(UUID(ATTEMPT_ID), CAPTURE_CONTEXT_TOOL))
    assert nutrition_id == str(uuid5(UUID(ATTEMPT_ID), NUTRITION_CONTEXT_TOOL))
    assert capture_id != nutrition_id
    assert capture_id == _stable_tool_call_id(ATTEMPT_ID, CAPTURE_CONTEXT_TOOL)
    with pytest.raises(ValueError, match="attempt_id must be a UUID"):
        _stable_tool_call_id("bad-id", CAPTURE_CONTEXT_TOOL)


def test_bindings_accept_iterables_and_normalized_prefixed_names():
    remotes = [
        FakeMcpTool("healthmind__orion_nutrition_context_get", "{}"),
        FakeMcpTool("healthmind__nutrimemo_capture_context_get", capture_context_payload()),
        FakeMcpTool("unapproved.write", "{}"),
    ]
    tools, called, presented = bind_context_tools(iter(remotes), task_id=TASK_ID, attempt_id=ATTEMPT_ID)
    assert [tool.name for tool in tools] == ["capture_context", "nutrition_context"]
    asyncio.run(tools[1].ainvoke({}))
    assert called == presented == {"nutrition_context"}
    assert remotes[0].calls == [{"taskId": TASK_ID, "attemptId": ATTEMPT_ID}]
    assert remotes[1].calls == remotes[2].calls == []


def test_ambiguous_allowlisted_tool_is_rejected_before_any_read():
    remotes = [
        FakeMcpTool(CAPTURE_CONTEXT_TOOL, "{}"),
        FakeMcpTool("prefix.nutrimemo.capture_context.get", "{}"),
        FakeMcpTool(NUTRITION_CONTEXT_TOOL, "{}"),
    ]
    with pytest.raises(McpSetupError, match="实际匹配 2 个") as caught:
        bind_context_tools(remotes, task_id=TASK_ID, attempt_id=ATTEMPT_ID)
    assert caught.value.stage == "list_tools"
    assert all(remote.calls == [] for remote in remotes)


def test_prefetched_capture_uses_cache_and_nutrition_remains_model_driven():
    capture = FakeMcpTool(CAPTURE_CONTEXT_TOOL, "not used")
    nutrition = FakeMcpTool(NUTRITION_CONTEXT_TOOL, '{"age_years":18}')
    cached = '{"notes":"米饭约半碗","confirmed_image_count":1}'
    tools, called, presented = bind_context_tools(
        [capture, nutrition], task_id=TASK_ID, attempt_id=ATTEMPT_ID,
        cached_context={"capture_context": cached},
    )
    assert capture.calls == nutrition.calls == []
    assert asyncio.run(tools[0].ainvoke({})) == cached
    assert presented == {"capture_context"}
    assert called == set()
    assert capture.calls == nutrition.calls == []
    assert json.loads(asyncio.run(tools[1].ainvoke({}))) == {"age_years": 18}
    assert called == {"nutrition_context"}
    assert len(nutrition.calls) == 1
    with pytest.raises(RuntimeError, match="only once"):
        asyncio.run(tools[0].ainvoke({}))
    with pytest.raises(RuntimeError, match="only once"):
        asyncio.run(tools[1].ainvoke({}))
    assert len(nutrition.calls) == 1


def test_failed_remote_is_not_retried_or_counted_and_preserves_cause():
    root_cause = OSError("offline transport failure")

    class FailingRemote(FakeMcpTool):
        async def ainvoke(self, arguments):
            self.calls.append(arguments)
            raise root_cause

    failing = FailingRemote(NUTRITION_CONTEXT_TOOL, None)
    tools, called, presented = bind_context_tools(
        [FakeMcpTool(CAPTURE_CONTEXT_TOOL, "{}"), failing], task_id=TASK_ID, attempt_id=ATTEMPT_ID,
    )
    with pytest.raises(McpSetupError) as caught:
        asyncio.run(tools[1].ainvoke({}))
    assert caught.value.stage == "tool:nutrition_context"
    assert caught.value.__cause__ is root_cause
    assert called == presented == set()
    with pytest.raises(RuntimeError, match="only once"):
        asyncio.run(tools[1].ainvoke({}))
    assert len(failing.calls) == 1


def test_is_error_response_is_not_presented_or_retried():
    failing = FakeMcpTool(NUTRITION_CONTEXT_TOOL, {"isError": True, "structuredContent": {"age_years": 18}})
    tools, called, presented = bind_context_tools(
        [FakeMcpTool(CAPTURE_CONTEXT_TOOL, "{}"), failing], task_id=TASK_ID, attempt_id=ATTEMPT_ID,
    )
    with pytest.raises(McpSetupError, match="tool returned an error"):
        asyncio.run(tools[1].ainvoke({}))
    with pytest.raises(RuntimeError, match="only once"):
        asyncio.run(tools[1].ainvoke({}))
    assert len(failing.calls) == 1
    assert called == presented == set()


def test_concurrent_model_invocations_make_at_most_one_remote_read():
    class SlowRemote(FakeMcpTool):
        async def ainvoke(self, arguments):
            self.calls.append(arguments)
            await asyncio.sleep(0)
            return "{}"

    nutrition = SlowRemote(NUTRITION_CONTEXT_TOOL, None)
    tools, called, presented = bind_context_tools(
        [FakeMcpTool(CAPTURE_CONTEXT_TOOL, "{}"), nutrition], task_id=TASK_ID, attempt_id=ATTEMPT_ID,
    )

    async def invoke():
        return await asyncio.gather(tools[1].ainvoke({}), tools[1].ainvoke({}), return_exceptions=True)

    outcomes = asyncio.run(invoke())
    assert outcomes[0] == "{}"
    assert isinstance(outcomes[1], RuntimeError)
    assert len(nutrition.calls) == 1
    assert called == presented == {"nutrition_context"}


def test_failed_tool_log_preserves_stage_and_cause_chain_and_removes_signed_urls():
    stream = io.StringIO()
    configure_logging(DebugLevel.TRACE, sink=stream, level="DEBUG", file_path=None, color="never", force=True)

    class FailingRemote(FakeMcpTool):
        async def ainvoke(self, arguments):
            try:
                raise OSError("offline remote https://media.example.test/image?token=never-log")
            except OSError as exception:
                raise RuntimeError("SDK read failed") from exception

    tools, _, _ = bind_context_tools(
        [FakeMcpTool(CAPTURE_CONTEXT_TOOL, "{}"), FailingRemote(NUTRITION_CONTEXT_TOOL, None)],
        task_id=TASK_ID, attempt_id=ATTEMPT_ID,
    )
    with pytest.raises(McpSetupError):
        asyncio.run(tools[1].ainvoke({}))
    output = stream.getvalue()
    assert 'mcp_stage="tool:nutrition_context"' in output
    assert "RuntimeError" in output
    assert "OSError" in output
    assert "direct cause" in output
    assert "media.example.test/image" not in output
    assert "never-log" not in output


def test_mcp_wrappers_inject_ids_and_remove_urls():
    capture = FakeMcpTool(
        "nutrimemo.capture_context.get",
        json.dumps(
            capture_context_payload(
                url="https://storage.invalid/photo?X-Amz-Signature=secret",
            )
        ),
    )
    nutrition = FakeMcpTool(
        "orion.nutrition_context.get",
        '{"subject_id":"user-id","allergies":[],"age_years":18}',
    )
    task_id = "11111111-1111-4111-8111-111111111111"
    attempt_id = "22222222-2222-4222-8222-222222222222"
    tools, called, presented = bind_context_tools([capture, nutrition], task_id=task_id, attempt_id=attempt_id)

    capture_result = asyncio.run(tools[0].ainvoke({}))
    nutrition_result = asyncio.run(tools[1].ainvoke({}))

    assert capture.calls == [{"taskId": task_id, "attemptId": attempt_id}]
    assert nutrition.calls == [{"taskId": task_id, "attemptId": attempt_id}]
    assert capture.metadata == [{"tool_call_id": _stable_tool_call_id(attempt_id, "nutrimemo.capture_context.get")}]
    assert nutrition.metadata == [{"tool_call_id": _stable_tool_call_id(attempt_id, "orion.nutrition_context.get")}]
    assert "X-Amz-Signature" not in capture_result
    assert "storage.invalid" not in capture_result
    assert "capture_session_id" not in capture_result
    assert json.loads(capture_result)["notes"] == "米饭约半碗"
    assert json.loads(capture_result)["confirmed_image_count"] == 1
    assert "subject_id" not in nutrition_result
    assert {"capture_context", "nutrition_context"} == called
    assert {"capture_context", "nutrition_context"} == presented


def test_sdk_mcp_adapter_uses_reserved_request_meta_for_stable_tool_call_id():
    class Session:
        def __init__(self):
            self.calls = []

        async def call_tool(self, name, *, arguments, meta):
            self.calls.append((name, arguments, meta))
            return {"structuredContent": capture_context_payload()}

    async def invoke():
        session = Session()
        attempt_id = "22222222-2222-4222-8222-222222222222"
        remote = [
            _McpSdkRemoteTool(session, "nutrimemo.capture_context.get"),
            _McpSdkRemoteTool(session, "orion.nutrition_context.get"),
        ]
        tools, _, _ = bind_context_tools(
            remote,
            task_id="11111111-1111-4111-8111-111111111111",
            attempt_id=attempt_id,
        )
        await tools[0].ainvoke({})
        await tools[1].ainvoke({})
        assert session.calls == [
            (
                "nutrimemo.capture_context.get",
                {"taskId": "11111111-1111-4111-8111-111111111111", "attemptId": attempt_id},
                {"tool_call_id": _stable_tool_call_id(attempt_id, "nutrimemo.capture_context.get")},
            ),
            (
                "orion.nutrition_context.get",
                {"taskId": "11111111-1111-4111-8111-111111111111", "attemptId": attempt_id},
                {"tool_call_id": _stable_tool_call_id(attempt_id, "orion.nutrition_context.get")},
            ),
        ]

    asyncio.run(invoke())


def test_mcp_structured_content_is_available_to_agent():
    message = ToolMessage(
        content="",
        artifact={"structured_content": capture_context_payload()},
        tool_call_id="mcp-test-call",
        name="capture_context",
    )
    remote = [
        FakeMcpTool("nutrimemo.capture_context.get", message),
        FakeMcpTool("orion.nutrition_context.get", "{}"),
    ]
    tools, _, _ = bind_context_tools(
        remote,
        task_id="11111111-1111-4111-8111-111111111111",
        attempt_id="22222222-2222-4222-8222-222222222222",
    )

    result = asyncio.run(tools[0].ainvoke({}))
    parsed = json.loads(result)
    assert parsed["meal_type"] == "lunch"
    assert parsed["confirmed_image_count"] == 1


def test_mcp_context_tool_is_limited_to_one_call():
    remote = [
        FakeMcpTool("nutrimemo.capture_context.get", json.dumps(capture_context_payload())),
        FakeMcpTool("orion.nutrition_context.get", "{}"),
    ]
    tools, _, _ = bind_context_tools(
        remote,
        task_id="11111111-1111-4111-8111-111111111111",
        attempt_id="22222222-2222-4222-8222-222222222222",
    )
    asyncio.run(tools[0].ainvoke({}))
    with pytest.raises(RuntimeError, match="only once"):
        asyncio.run(tools[0].ainvoke({}))


def test_mcp_failed_call_is_not_counted_as_successful():
    class FailingMcpTool(FakeMcpTool):
        async def ainvoke(self, arguments):
            raise RuntimeError("private remote error")

    remote = [
        FailingMcpTool("nutrimemo.capture_context.get", "{}"),
        FakeMcpTool("orion.nutrition_context.get", "{}"),
    ]
    tools, called, _ = bind_context_tools(
        remote,
        task_id="11111111-1111-4111-8111-111111111111",
        attempt_id="22222222-2222-4222-8222-222222222222",
    )
    with pytest.raises(RuntimeError, match="MCP read failed"):
        asyncio.run(tools[0].ainvoke({}))
    assert called == set()


def test_mcp_tools_must_match_both_allowlisted_reads():
    only_capture = [FakeMcpTool("nutrimemo.capture_context.get", "{}")]
    with pytest.raises(RuntimeError, match="orion.nutrition_context.get"):
        bind_context_tools(
            only_capture,
            task_id="11111111-1111-4111-8111-111111111111",
            attempt_id="22222222-2222-4222-8222-222222222222",
        )
