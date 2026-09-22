"""① 纯 StateGraph 样板：状态、节点、条件边、reducer。

这一段**不调用任何模型**，离线就能跑，目的是先看清 LangGraph 的图本身长什么样。
这里做的是一个玩具级「描述质检」，不是真实的膳食分析。
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

MIN_LENGTH = 5
DEFAULT_TEXT = "午饭吃了番茄炒蛋和米饭"


class ReviewState(TypedDict):
    """图的共享状态。

    LangGraph 的节点就是「读状态 → 返回增量」的普通函数：
    返回的字典会按字段被合并回状态，不需要自己拼整个状态对象。
    """

    text: str

    # Annotated[..., operator.add] 是 reducer，决定同名字段怎么合并。
    # 有它：多个节点写入的 list 会相加累积；没有它：后写的直接覆盖先写的。
    notes: Annotated[list[str], operator.add]

    route: str


def normalize(state: ReviewState) -> dict:
    """节点一：规整输入。只返回自己负责的字段。"""
    text = state["text"].strip()
    return {"text": text, "notes": [f"normalize: 规整后长度 {len(text)}"]}


def judge(state: ReviewState) -> dict:
    """节点二：纯规则判定，结果写进 route 供条件边读取。"""
    route = "accept" if len(state["text"]) >= MIN_LENGTH else "reject"
    return {"route": route, "notes": [f"judge: 判定为 {route}"]}


def accept(state: ReviewState) -> dict:
    """分支终结点：描述够具体。"""
    return {"notes": ["accept: 描述够具体，可以进入下一步分析"]}


def reject(state: ReviewState) -> dict:
    """分支终结点：描述太短。"""
    return {"notes": ["reject: 描述太短，需要用户补充"]}


def pick_branch(state: ReviewState) -> str:
    """条件边的选路函数：返回值被拿去查下面的映射表。"""
    return state["route"]


def build_graph():
    """组装并编译图。

        START → normalize → judge ─┬─ accept → END
                                   └─ reject → END
    """
    graph = StateGraph(ReviewState)

    graph.add_node("normalize", normalize)
    graph.add_node("judge", judge)
    graph.add_node("accept", accept)
    graph.add_node("reject", reject)

    graph.add_edge(START, "normalize")
    graph.add_edge("normalize", "judge")

    # 条件边 = 选路函数 + 返回值到节点名的映射表。
    graph.add_conditional_edges(
        "judge",
        pick_branch,
        {"accept": "accept", "reject": "reject"},
    )

    graph.add_edge("accept", END)
    graph.add_edge("reject", END)

    return graph.compile()


def run(text: str = DEFAULT_TEXT) -> ReviewState:
    """跑一遍图：先看每个节点返回的增量，再看合并后的最终状态。"""
    app = build_graph()
    initial: ReviewState = {"text": text, "notes": [], "route": ""}

    print(f"输入：{text!r}")
    print("--- stream：每个节点执行后返回的增量 ---")
    # 默认 stream_mode="updates"，逐节点产出 {节点名: 该节点的返回值}。
    for step in app.stream(initial):
        for node_name, update in step.items():
            print(f"[{node_name}] {update}")

    result = app.invoke(initial)
    print("--- 最终状态（notes 因 reducer 而累积）---")
    for note in result["notes"]:
        print(f"  · {note}")
    print(f"  route = {result['route']}")
    return result


if __name__ == "__main__":
    run()
