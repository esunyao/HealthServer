"""CLI argument syntax retained for scripts and interactive usage."""

import argparse
import os
from uuid import UUID
from ..examples.basic_graph import DEFAULT_TEXT
from ..examples.simple_agent import DEFAULT_QUESTION


def _uuid_argument(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exception:
        raise argparse.ArgumentTypeError("必须是 UUID") from exception


def _add_debug_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--debug",
        nargs="?",
        const="trace",
        default=None,
        choices=("off", "trace", "full"),
        type=str.lower,
        help="输出调试轨迹；省略值等价 trace，full 仅限本地开发",
    )


def _apply_debug_argument(args: argparse.Namespace) -> None:
    value = getattr(args, "debug", None)
    if value is not None:
        os.environ["NUTRIATHENA_DEBUG"] = value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nutriathena-agent")
    commands = parser.add_subparsers(dest="command")
    graph = commands.add_parser("graph", help="运行离线 LangGraph 教学示例")
    graph.add_argument("text", nargs="?", default=DEFAULT_TEXT)
    agent = commands.add_parser("agent", help="运行最小 LangChain agent 教学示例")
    agent.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    serve = commands.add_parser(
        "serve", help="启动 HealthMind-compatible HTTP 服务和持久 worker"
    )
    _add_debug_argument(serve)
    commands.add_parser("migrate", help="应用校验和保护的 PostgreSQL 版本迁移")
    meal = commands.add_parser(
        "meal", help="直接运行一个 HealthMind 餐食 attempt（生产使用 serve）"
    )
    _add_debug_argument(meal)
    meal.add_argument("--task-id", required=True, type=_uuid_argument)
    meal.add_argument("--attempt-id", required=True, type=_uuid_argument)
    meal.add_argument("--trace-id", default="manual-run", help="调用链追踪标识")
    smoke = commands.add_parser(
        "smoke", help="通过 OAuth 对已部署服务运行安全真实 smoke"
    )
    smoke.add_argument("--task-id", required=True, type=_uuid_argument)
    smoke.add_argument("--attempt-id", required=True, type=_uuid_argument)
    smoke.add_argument("--trace-id", required=True)
    parser.set_defaults(command="graph", text=DEFAULT_TEXT)
    return parser
