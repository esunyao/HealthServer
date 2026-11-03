"""CLI for the service runtime and retained LangGraph teaching examples."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from uuid import UUID

from .basic_graph import DEFAULT_TEXT, run as run_graph
from .config import load_env
from .logging_service import configure_logging, log_event, log_exception, parse_debug_level
from .simple_agent import DEFAULT_QUESTION, run as run_agent


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
    serve = commands.add_parser("serve", help="启动 HealthMind-compatible HTTP 服务和持久 worker")
    _add_debug_argument(serve)
    commands.add_parser("migrate", help="应用校验和保护的 PostgreSQL 版本迁移")
    meal = commands.add_parser("meal", help="直接运行一个 HealthMind 餐食 attempt（生产使用 serve）")
    _add_debug_argument(meal)
    meal.add_argument("--task-id", required=True, type=_uuid_argument)
    meal.add_argument("--attempt-id", required=True, type=_uuid_argument)
    meal.add_argument("--trace-id", default="manual-run", help="调用链追踪标识")
    smoke = commands.add_parser("smoke", help="通过 OAuth 对已部署服务运行安全真实 smoke")
    smoke.add_argument("--task-id", required=True, type=_uuid_argument)
    smoke.add_argument("--attempt-id", required=True, type=_uuid_argument)
    smoke.add_argument("--trace-id", required=True)
    parser.set_defaults(command="graph", text=DEFAULT_TEXT)
    return parser


def _migrate() -> int:
    load_env()
    database_url = os.environ.get("NUTRIATHENA_DATABASE_URL", "").strip()
    if not database_url:
        log_event(
            "migration.config.missing",
            level="ERROR",
            message="缺少运行配置：NUTRIATHENA_DATABASE_URL",
        )
        return 2
    from .api import migrate_database

    try:
        applied = migrate_database(database_url)
    except Exception as exception:
        log_exception("migration.failed", exception)
        return 2
    print(json.dumps({"applied": applied}, ensure_ascii=False, separators=(",", ":")))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _apply_debug_argument(args)
    load_env()
    configure_logging(parse_debug_level(os.environ.get("NUTRIATHENA_DEBUG", "off")))
    if args.command == "graph":
        run_graph(args.text)
        return 0
    if args.command == "agent":
        run_agent(args.question)
        return 0
    if args.command == "migrate":
        return _migrate()
    if args.command == "serve":
        from .api import create_app
        from .runtime_config import load_runtime_settings
        import uvicorn

        try:
            settings = load_runtime_settings()
            configure_logging(settings.debug_level, intercept_stdlib=True, force=True)
            log_event(
                "service.starting",
                level="INFO",
                host=settings.host,
                port=settings.port,
                release_id=str(settings.release_id),
                deployment_key=settings.deployment_key,
                assistant_id=settings.assistant_id,
            )
            app = create_app(settings=settings)
            uvicorn.run(
                app,
                host=settings.host,
                port=settings.port,
                log_config=None,
                access_log=False,
            )
        except Exception as exception:
            log_exception("service.failed", exception)
            return 2
        return 0
    if args.command == "meal":
        from .meal_agent import run_meal_analysis

        try:
            result = asyncio.run(
                run_meal_analysis(
                    task_id=args.task_id,
                    attempt_id=args.attempt_id,
                    trace_id=args.trace_id,
                )
            )
        except Exception as exception:
            log_event(
                "cli.meal.failed",
                level="ERROR",
                trace_id=args.trace_id,
                task_id=args.task_id,
                attempt_id=args.attempt_id,
                error_type=type(exception).__name__,
                error_message=str(exception),
            )
            return 2
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    if args.command == "smoke":
        from .smoke import run_smoke

        try:
            result = asyncio.run(
                run_smoke(task_id=args.task_id, attempt_id=args.attempt_id, trace_id=args.trace_id)
            )
        except Exception as exception:
            log_exception("smoke.failed", exception)
            return 2
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        if result.get("status") == "success" and result.get("output_status") == "analysis":
            return 0
        return 2 if result.get("status") in {"error", "interrupted", "success"} else 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
