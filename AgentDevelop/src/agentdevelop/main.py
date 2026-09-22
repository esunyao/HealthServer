"""命令行入口：把两段样板串起来。

    uv run agentdevelop graph [文本]     # ① 纯图，不调用模型，离线可跑
    uv run agentdevelop agent [问题]     # ② 最小 agent，会调用模型，需要 .env
"""

from __future__ import annotations

import argparse

from .basic_graph import DEFAULT_TEXT, run as run_graph
from .simple_agent import DEFAULT_QUESTION, run as run_agent


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agentdevelop",
        description="AgentDevelop 的 LangGraph 学习样板",
    )
    sub = parser.add_subparsers(dest="command")

    p_graph = sub.add_parser("graph", help="① 纯 StateGraph：不调用模型，离线可跑")
    p_graph.add_argument("text", nargs="?", default=DEFAULT_TEXT, help="输入的一句话描述")

    p_agent = sub.add_parser("agent", help="② 最小 agent：调用模型，需要 .env")
    p_agent.add_argument("question", nargs="?", default=DEFAULT_QUESTION, help="要问的问题")

    args = parser.parse_args()

    if args.command == "agent":
        run_agent(args.question)
        return

    # 不带子命令时默认跑离线那段。两段都不会在 import 期校验凭据：
    # 只有 build_model() 实例化模型时才需要 key，第①段根本不会走到那里。
    run_graph(args.text if args.command == "graph" else DEFAULT_TEXT)


if __name__ == "__main__":
    main()
