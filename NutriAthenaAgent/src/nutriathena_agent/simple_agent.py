"""② 最小 agent 样板：create_agent + 一个自定义工具。

这一段会真正调用模型，需要先按 `.env.example` 配好 `.env`。

注意用的是 `langchain.agents.create_agent`；
`langgraph.prebuilt.create_react_agent` 已被官方标记废弃，新代码不要再用。
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.tools import tool

from .config import build_model

SYSTEM_PROMPT = "你是一个简洁的助手。需要数词数时调用 word_count 工具，不要自己估算。"
DEFAULT_QUESTION = "统计一下这句话的词数：今天午饭吃了番茄炒蛋"


@tool
def word_count(text: str) -> int:
    """统计一段文本的词数（按空白切分）。"""
    # 工具的 docstring 就是给模型看的说明，写清楚它会怎么用。
    return len(text.split())


def build_agent():
    """create_agent 返回的是一张编译好的 LangGraph 图，可直接 invoke。"""
    return create_agent(
        model=build_model(),
        tools=[word_count],
        system_prompt=SYSTEM_PROMPT,
    )


def run(question: str = DEFAULT_QUESTION) -> str:
    """问一个问题，打印完整消息轨迹，让 agent 的工具循环可见。"""
    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})

    print(f"提问：{question}")
    print("--- 消息轨迹 ---")
    for message in result["messages"]:
        # 依次会看到：HumanMessage → AIMessage(带 tool_calls) → ToolMessage → AIMessage(最终回答)
        tool_calls = getattr(message, "tool_calls", None)
        suffix = f"  tool_calls={tool_calls}" if tool_calls else ""
        print(f"[{type(message).__name__}] {message.content!r}{suffix}")

    answer = result["messages"][-1].content
    print("--- 最终回答 ---")
    print(answer)
    return answer


if __name__ == "__main__":
    run()
