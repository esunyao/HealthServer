"""CLI for the LangGraph examples and the standalone meal-analysis agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import UUID

from .basic_graph import DEFAULT_TEXT, run as run_graph
from .simple_agent import DEFAULT_QUESTION, run as run_agent


def _uuid_argument(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exception:
        raise argparse.ArgumentTypeError("必须是 UUID") from exception


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentdevelop")
    commands = parser.add_subparsers(dest="command")
    graph = commands.add_parser("graph", help="运行离线 LangGraph 教学示例")
    graph.add_argument("text", nargs="?", default=DEFAULT_TEXT)
    agent = commands.add_parser("agent", help="运行最小 LangChain agent 教学示例")
    agent.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    meal = commands.add_parser("meal", help="运行独立餐食分析 DeepAgent")
    meal.add_argument("--task-id", required=True, type=_uuid_argument)
    meal.add_argument("--attempt-id", required=True, type=_uuid_argument)
    meal.add_argument("--image", required=True, action="append", help="本地 JPEG、PNG 或 WebP；可重复传入")
    meal.add_argument("--evidence", help="调用方导出的知识库证据 JSON（最大 1 MiB）")
    meal.add_argument("--note", default="", help="用户明确提供的餐食备注")
    parser.set_defaults(command="graph")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "graph":
        run_graph(args.text)
        return 0
    if args.command == "agent":
        run_agent(args.question)
        return 0
    if args.command == "meal":
        from .meal_agent import run_meal_analysis

        try:
            result = asyncio.run(
                run_meal_analysis(
                    task_id=args.task_id,
                    attempt_id=args.attempt_id,
                    image_paths=args.image,
                    evidence_path=args.evidence,
                    note=args.note,
                )
            )
        except Exception as exception:
            print(f"餐食 Agent 运行失败：{type(exception).__name__}: {exception}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
