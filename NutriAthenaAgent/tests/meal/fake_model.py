"""A finite, provider-free model that exercises the real agent tool loop."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedMealModel(BaseChatModel):
    responses: list[AIMessage]
    requests: list[list[BaseMessage]] = Field(default_factory=list)
    tool_bindings: list[list[str]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "offline-scripted-meal-model"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs: Any):
        assert tool_choice is None
        assert not kwargs, "The meal loop must not configure structured-output repair"
        self.tool_bindings.append([item.name for item in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        del stop, run_manager, kwargs
        index = len(self.requests)
        self.requests.append(list(messages))
        if index >= len(self.responses):
            raise AssertionError("Unexpected extra model call beyond the scripted tool loop")
        return ChatResult(generations=[ChatGeneration(message=self.responses[index])])
