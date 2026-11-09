"""Build the meal agent with only its two authorized context reads."""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

REQUIRED_CONTEXT_TOOLS = frozenset({"capture_context", "nutrition_context"})


def build_meal_agent(model: BaseChatModel, tools: list[BaseTool], system_prompt: str):
    """Compile the standard tool loop with the exact read-only MCP tool set."""
    if len(tools) != len(REQUIRED_CONTEXT_TOOLS) or {tool.name for tool in tools} != REQUIRED_CONTEXT_TOOLS:
        raise ValueError("餐食 Agent 必须仅注册 capture_context 与 nutrition_context 两个只读 MCP 工具")
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        name="healthmind-meal-analysis",
    )
