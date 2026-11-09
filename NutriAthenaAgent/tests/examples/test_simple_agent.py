"""Exercise the teaching agent without constructing a provider client."""

from __future__ import annotations

import socket

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from pydantic import Field

from nutriathena_agent.examples import basic_graph, simple_agent


class WordCountModel(FakeMessagesListChatModel):
    requests: list[list] = Field(default_factory=list)
    bound_tools: list[str] = Field(default_factory=list)

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        assert tool_choice is None
        assert not kwargs
        self.bound_tools = [item.name for item in tools]
        return self

    def _generate(self, messages, *args, **kwargs):
        self.requests.append(list(messages))
        assert len(self.requests) <= 2, "Unexpected extra example model call"
        return super()._generate(messages, *args, **kwargs)


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Example tests must not use the network")

    async def forbidden_async(*args, **kwargs):
        raise AssertionError("Example tests must not use the network")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden_async)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")


def test_simple_agent_retains_default_question_and_executes_word_count(monkeypatch, capsys):
    model = WordCountModel(responses=[
        AIMessage(content="", tool_calls=[{
            "name": "word_count", "args": {"text": "今天 午饭 番茄炒蛋"}, "id": "count-1",
        }]),
        AIMessage(content="3 个词"),
    ])
    monkeypatch.setattr(simple_agent, "build_model", lambda: model)

    assert simple_agent.run() == "3 个词"

    assert model.bound_tools == ["word_count"]
    assert len(model.requests) == 2
    assert model.requests[0][0].content == simple_agent.SYSTEM_PROMPT
    assert model.requests[0][1].content == "统计一下这句话的词数：今天午饭吃了番茄炒蛋"
    assert model.requests[1][-1].name == "word_count"
    assert model.requests[1][-1].content == "3"
    printed = capsys.readouterr().out
    assert "[ToolMessage]" in printed
    assert "3 个词" in printed


@pytest.mark.parametrize("text,expected", [("", 0), ("今天午饭", 1), ("  今天  午饭\n米饭  ", 3)])
def test_word_count_uses_whitespace(text, expected):
    assert simple_agent.word_count.invoke({"text": text}) == expected


def test_basic_graph_run_retains_default_input_and_prints_updates(capsys):
    result = basic_graph.run()

    assert basic_graph.DEFAULT_TEXT == "午饭吃了番茄炒蛋和米饭"
    assert result["text"] == basic_graph.DEFAULT_TEXT
    assert result["route"] == "accept"
    assert len(result["notes"]) == 3
    printed = capsys.readouterr().out
    assert "[normalize]" in printed
    assert "[judge]" in printed
    assert "[accept]" in printed
