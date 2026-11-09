from __future__ import annotations

import asyncio
import io
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from nutriathena_agent.observability import (
    DebugLevel, LogFormat, DebugTraceCallback, DebugTracer, configure_logging,
)


def _capture(level: DebugLevel) -> io.StringIO:
    stream = io.StringIO()
    configure_logging(
        level,
        sink=stream,
        log_format=LogFormat.TEXT,
        level="DEBUG",
        file_path=None,
        color="never",
        force=True,
    )
    return stream



def test_callback_trace_level_records_structure_without_content():
    stream = _capture(DebugLevel.TRACE)
    tracer = DebugTracer(DebugLevel.TRACE, trace_id="trace-test")
    callback = DebugTraceCallback(tracer)
    run_id = uuid4()
    messages = [
        [
            HumanMessage(
                content=[
                    {"type": "text", "text": "secret meal note"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}},
                ]
            )
        ]
    ]
    response = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content='{"items":[{"name":"米饭"}]}'))]],
        llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
    )

    asyncio.run(callback.on_chat_model_start({}, messages, run_id=run_id))
    asyncio.run(callback.on_llm_end(response, run_id=run_id))

    output = stream.getvalue()
    assert "event=llm.started" in output
    assert "image_parts=1" in output
    assert "event=llm.finished" in output
    assert "prompt_tokens=10" in output
    assert "completion_tokens=5" in output
    assert "total_tokens=15" in output
    assert "secret meal note" not in output
    assert "米饭" not in output
    assert "base64,QUJD" not in output



def test_callback_full_level_redacts_content():
    stream = _capture(DebugLevel.FULL)
    tracer = DebugTracer(DebugLevel.FULL, trace_id="trace-test")
    callback = DebugTraceCallback(tracer)
    run_id = uuid4()
    messages = [
        [
            HumanMessage(
                content=[
                    {"type": "text", "text": "secret meal note"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}},
                ]
            )
        ]
    ]
    response = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content='{"items":[{"name":"米饭"}]}'))]],
        llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}},
    )

    asyncio.run(callback.on_chat_model_start({}, messages, run_id=run_id))
    asyncio.run(callback.on_llm_end(response, run_id=run_id))

    output = stream.getvalue()
    assert "secret meal note" in output
    assert "米饭" in output
    assert "[image omitted: image/jpeg]" in output
    assert "base64,QUJD" not in output



def test_callback_chain_events_only_for_langgraph_nodes():
    stream = _capture(DebugLevel.TRACE)
    tracer = DebugTracer(DebugLevel.TRACE)
    callback = DebugTraceCallback(tracer)
    node_run = uuid4()
    child_run = uuid4()

    asyncio.run(
        callback.on_chain_start(
            {},
            {},
            run_id=node_run,
            metadata={"langgraph_node": "model"},
            name="model",
        )
    )
    asyncio.run(
        callback.on_chain_start(
            {},
            {},
            run_id=child_run,
            metadata={"langgraph_node": "model"},
            name="RunnableSequence",
        )
    )
    asyncio.run(callback.on_chain_end({}, run_id=child_run))
    asyncio.run(callback.on_chain_end({}, run_id=node_run))

    output = stream.getvalue()
    assert output.count("event=node.started") == 1
    assert output.count("event=node.finished") == 1



def test_callback_tool_events_record_duration_and_redact_output():
    stream = _capture(DebugLevel.FULL)
    tracer = DebugTracer(DebugLevel.FULL)
    callback = DebugTraceCallback(tracer)
    run_id = uuid4()

    asyncio.run(callback.on_tool_start({"name": "capture_context"}, "{}", run_id=run_id))
    asyncio.run(callback.on_tool_end("https://media.example.test/x?token=secret", run_id=run_id))

    output = stream.getvalue()
    assert "event=tool.started" in output
    assert 'tool="capture_context"' in output
    assert "event=tool.finished" in output
    assert "duration_ms=" in output
    assert "[URL removed]" in output
    assert "token=secret" not in output



def test_callback_tool_error_only_records_type_at_trace_level():
    stream = _capture(DebugLevel.TRACE)
    tracer = DebugTracer(DebugLevel.TRACE)
    callback = DebugTraceCallback(tracer)
    run_id = uuid4()

    asyncio.run(callback.on_tool_start({"name": "nutrition_context"}, "{}", run_id=run_id))
    asyncio.run(callback.on_tool_error(RuntimeError("secret https://x.test"), run_id=run_id))

    output = stream.getvalue()
    assert "event=tool.error" in output
    assert 'error_type="RuntimeError"' in output
    assert "secret" not in output
    assert "x.test" not in output

