"""Dispatch commands without eager network configuration."""
import asyncio
import json
import os
from ..config import load_env
from ..logging_service import configure_logging, log_event, log_exception, parse_debug_level
from ..examples.basic_graph import DEFAULT_TEXT, run as run_graph
from ..examples.simple_agent import run as run_agent
from .parser import build_parser, _apply_debug_argument

def _migrate() -> int:
    load_env()
    database_url = os.environ.get('NUTRIATHENA_DATABASE_URL', '').strip()
    if not database_url:
        log_event('migration.config.missing', level='ERROR', message='缺少运行配置：NUTRIATHENA_DATABASE_URL')
        return 2
    from ..runtime.migration import migrate_database
    try:
        applied = migrate_database(database_url)
    except Exception as exception:
        log_exception('migration.failed', exception)
        return 2
    print(json.dumps({'applied': applied}, ensure_ascii=False, separators=(',', ':')))
    return 0

def main(argv: list[str] | None=None) -> int:
    args = build_parser().parse_args(argv)
    _apply_debug_argument(args)
    load_env()
    configure_logging(parse_debug_level(os.environ.get('NUTRIATHENA_DEBUG', 'off')))
    if args.command == 'graph':
        run_graph(args.text)
        return 0
    if args.command == 'agent':
        run_agent(args.question)
        return 0
    if args.command == 'migrate':
        return _migrate()
    if args.command == 'serve':
        from ..api import create_app
        from ..config import load_runtime_settings
        import uvicorn
        try:
            settings = load_runtime_settings()
            configure_logging(settings.debug_level, intercept_stdlib=True, force=True)
            log_event('service.starting', level='INFO', host=settings.host, port=settings.port, release_id=str(settings.release_id), deployment_key=settings.deployment_key, assistant_id=settings.assistant_id)
            app = create_app(settings=settings)
            uvicorn.run(app, host=settings.host, port=settings.port, log_config=None, access_log=False)
        except Exception as exception:
            log_exception('service.failed', exception)
            return 2
        return 0
    if args.command == 'meal':
        from ..meal.runner import run_meal_analysis
        try:
            result = asyncio.run(run_meal_analysis(task_id=args.task_id, attempt_id=args.attempt_id, trace_id=args.trace_id))
        except Exception as exception:
            log_event('cli.meal.failed', level='ERROR', trace_id=args.trace_id, task_id=args.task_id, attempt_id=args.attempt_id, error_type=type(exception).__name__, error_message=str(exception))
            return 2
        print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
        return 0
    if args.command == 'smoke':
        from .smoke import run_smoke
        try:
            result = asyncio.run(run_smoke(task_id=args.task_id, attempt_id=args.attempt_id, trace_id=args.trace_id))
        except Exception as exception:
            log_exception('smoke.failed', exception)
            return 2
        print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
        if result.get('status') == 'success' and result.get('output_status') == 'analysis':
            return 0
        return 2 if result.get('status') in {'error', 'interrupted', 'success'} else 3
    return 2
