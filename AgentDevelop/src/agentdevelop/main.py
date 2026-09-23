"""命令行入口：把两段样板串起来。

    uv run agentdevelop graph [文本]     # ① 纯图，不调用模型，离线可跑
    uv run agentdevelop agent [问题]     # ② 最小 agent，会调用模型，需要 .env
"""

from __future__ import annotations

import argparse

from .basic_graph import DEFAULT_TEXT, run as run_graph
from .simple_agent import DEFAULT_QUESTION, run as run_agent
from deepagents import create_deep_agent

def main() -> None:
    agent = create_deep_agent()
    agent.invoke({"messages": [{"role": "user", "content": "Hello!"}]})


if __name__ == "__main__":
    main()
