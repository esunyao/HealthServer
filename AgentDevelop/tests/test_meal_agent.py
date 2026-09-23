from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI

from agentdevelop.contracts import MealAnalysis, NeedsReview, parse_meal_result, result_dict
from agentdevelop.dietary_prompt import build_system_prompt
from agentdevelop.images import ImageInputError, image_message_parts, load_local_images
from agentdevelop.meal_agent import build_meal_agent
from agentdevelop.mcp_tools import bind_context_tools


def test_local_images_preserve_order_and_encode_supported_types(tmp_path):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.png"
    first.write_bytes(b"\xff\xd8\xfffirst")
    second.write_bytes(b"\x89PNG\r\n\x1a\nsecond")

    images = load_local_images([first, second])
    parts = image_message_parts(images)

    assert [image.path.name for image in images] == ["first.jpg", "second.png"]
    assert [image.mime_type for image in images] == ["image/jpeg", "image/png"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert parts[3]["image_url"]["url"].startswith("data:image/png;base64,")


def test_local_images_reject_invalid_format_and_limits(tmp_path):
    invalid = tmp_path / "fake.jpg"
    invalid.write_bytes(b"not an image")
    with pytest.raises(ImageInputError, match="格式不支持"):
        load_local_images([invalid])

    valid = tmp_path / "large.jpg"
    valid.write_bytes(b"\xff\xd8\xffdata")
    with pytest.raises(ImageInputError, match="单张图片超过"):
        load_local_images([valid], max_image_bytes=4)

    with pytest.raises(ImageInputError, match="最多 1 张"):
        load_local_images([valid, valid], max_images=1)


def test_contract_accepts_success_and_review_objects():
    success = parse_meal_result(
        json.dumps(
            {
                "overall_confidence": 0.82,
                "items": [
                    {
                        "name": "熟米饭",
                        "weight_grams": 180,
                        "confidence": 0.9,
                        "nutrients": [{"code": "ENERGY_KCAL", "value": 209}],
                    }
                ],
            }
        )
    )
    review = parse_meal_result(
        '{"status":"needs_review","reason_code":"WEIGHT_UNSUPPORTED","message":"重量缺少依据"}'
    )

    assert isinstance(success, MealAnalysis)
    assert isinstance(review, NeedsReview)
    assert result_dict(review)["reason_code"] == "WEIGHT_UNSUPPORTED"


@pytest.mark.parametrize(
    "payload",
    [
        '{"overall_confidence":0.8,"items":[],"task_id":"not allowed"}',
        '{"overall_confidence":0.8,"items":[{"name":"饭","weight_grams":0,"confidence":0.8,"nutrients":[{"code":"ENERGY_KCAL","value":1}]}]}',
        '{"overall_confidence":0.8,"items":[{"name":"饭","weight_grams":100,"confidence":0.8,"nutrients":[{"code":"ENERGY_KCAL","value":1},{"code":"ENERGY_KCAL","value":2}]}]}',
        '{"overall_confidence":0.8,"items":[{"name":"饭","weight_grams":"100","confidence":0.8,"nutrients":[{"code":"ENERGY_KCAL","value":1}]}]}',
        '{"status":"needs_review","reason_code":"OTHER","message":"复核"}',
        '```json\n{}\n```',
    ],
)
def test_contract_rejects_invalid_or_wrapped_results(payload):
    with pytest.raises((ValidationError, ValueError)):
        parse_meal_result(payload)


class FakeMcpTool:
    def __init__(self, name: str, result: str):
        self.name = name
        self.result = result
        self.calls: list[dict[str, str]] = []

    async def ainvoke(self, arguments):
        arguments = arguments.get("args", arguments)
        self.calls.append(arguments)
        return self.result


def test_mcp_wrappers_inject_ids_and_remove_urls():
    capture = FakeMcpTool(
        "nutrimemo.capture_context.get",
        json.dumps(
            {
                "capture_session_id": "capture-id",
                "meal_id": 123,
                "meal_type": "lunch",
                "image_urls": [{"url": "https://storage.invalid/photo?X-Amz-Signature=secret"}],
                "imageURL": "https://storage.invalid/another?token=secret",
            }
        ),
    )
    nutrition = FakeMcpTool(
        "orion.nutrition_context.get",
        '{"subject_id":"user-id","allergies":[],"age_years":18}',
    )
    task_id = "11111111-1111-4111-8111-111111111111"
    attempt_id = "22222222-2222-4222-8222-222222222222"
    tools, called = bind_context_tools([capture, nutrition], task_id=task_id, attempt_id=attempt_id)

    capture_result = asyncio.run(tools[0].ainvoke({}))
    nutrition_result = asyncio.run(tools[1].ainvoke({}))

    assert capture.calls == [{"taskId": task_id, "attemptId": attempt_id}]
    assert nutrition.calls == [{"taskId": task_id, "attemptId": attempt_id}]
    assert "X-Amz-Signature" not in capture_result
    assert "storage.invalid" not in capture_result
    assert "capture_session_id" not in capture_result
    assert json.loads(capture_result)["confirmed_image_count"] == 1
    assert "subject_id" not in nutrition_result
    assert {"capture_context", "nutrition_context"} == called


def test_mcp_structured_content_is_available_to_agent():
    message = ToolMessage(
        content="",
        artifact={"structured_content": {"meal_type": "lunch", "confirmed": True}},
        tool_call_id="mcp-test-call",
        name="capture_context",
    )
    remote = [
        FakeMcpTool("nutrimemo.capture_context.get", message),
        FakeMcpTool("orion.nutrition_context.get", "{}"),
    ]
    tools, _ = bind_context_tools(
        remote,
        task_id="11111111-1111-4111-8111-111111111111",
        attempt_id="22222222-2222-4222-8222-222222222222",
    )

    result = asyncio.run(tools[0].ainvoke({}))
    parsed = json.loads(result)
    assert parsed["meal_type"] == "lunch"
    assert parsed["confirmed_image_count"] == 0


def test_mcp_context_tool_is_limited_to_one_call():
    remote = [
        FakeMcpTool("nutrimemo.capture_context.get", "{}"),
        FakeMcpTool("orion.nutrition_context.get", "{}"),
    ]
    tools, _ = bind_context_tools(
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
    tools, called = bind_context_tools(
        remote,
        task_id="11111111-1111-4111-8111-111111111111",
        attempt_id="22222222-2222-4222-8222-222222222222",
    )
    with pytest.raises(RuntimeError, match="MCP read failed"):
        asyncio.run(tools[0].ainvoke({}))
    assert called == set()


def test_deep_agent_dispatch_surface_contains_only_readonly_mcp_tools():
    async def noop() -> str:
        return "{}"

    mcp_tools = [
        StructuredTool.from_function(coroutine=noop, name=name, description="authorized read")
        for name in ("capture_context", "nutrition_context")
    ]
    model = ChatOpenAI(
        model="agent-isolation-test",
        api_key="test-only",
        base_url="https://example.invalid/v1",
    )
    agent = build_meal_agent(model, mcp_tools, "test prompt")

    dispatch = agent.nodes["tools"].bound._tools_by_name
    assert set(dispatch) == {"capture_context", "nutrition_context"}


def test_mcp_tools_must_match_both_allowlisted_reads():
    only_capture = [FakeMcpTool("nutrimemo.capture_context.get", "{}")]
    with pytest.raises(RuntimeError, match="orion.nutrition_context.get"):
        bind_context_tools(
            only_capture,
            task_id="11111111-1111-4111-8111-111111111111",
            attempt_id="22222222-2222-4222-8222-222222222222",
        )


def test_prompt_uses_adjacent_maintained_skills():
    prompt = build_system_prompt()

    assert "diet-result-contract/SKILL.md" in prompt
    assert "meal-evidence-analysis/references/calculation.md" in prompt
    assert "不要自行请求 URL" in prompt
    assert "不得声称检索过知识库" in prompt
    assert "本次运行的最终优先规则" in prompt
    assert "weight_grams" in prompt
