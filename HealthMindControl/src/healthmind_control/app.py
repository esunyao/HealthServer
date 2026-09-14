import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api import auditlog as auditlog_api
from .api import events as events_api
from .api import kafka as kafka_api
from .api import overview as overview_api
from .api import recovery as recovery_api
from .api import releases as releases_api
from .api import rows as rows_api
from .api import tasks as tasks_api
from .api import trace as trace_api
from .audit import AuditLog
from .config import settings
from .db import Database
from .repositories import Repository
from .security import PreviewStore
from .services import DifyService, KafkaService
from .ui import fmt as ui_fmt
from .ui import parts_router, ui_router

PACKAGE = Path(__file__).parent

ROUTERS = (
    overview_api.router,
    tasks_api.router,
    rows_api.router,
    trace_api.router,
    kafka_api.router,
    releases_api.router,
    recovery_api.router,
    auditlog_api.router,
    events_api.router,
    parts_router,
    ui_router,
)


def create_app() -> FastAPI:
    """装配应用：lifespan 注入共享服务；模块级 app 供 uvicorn 引用。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        missing = settings.missing_external_envs()
        if missing:
            raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
        app.state.csrf_token = secrets.token_urlsafe(32)
        app.state.previews = PreviewStore(settings.preview_ttl_seconds)
        app.state.audit = AuditLog(settings.audit_path)
        app.state.refresh_seconds = settings.refresh_seconds
        app.state.db = Database(settings)
        await app.state.db.open()
        app.state.repo = Repository(app.state.db, settings.stale_minutes, settings.task_retention_days)
        app.state.kafka = KafkaService(settings)
        app.state.dify = DifyService(settings)
        yield
        await app.state.db.close()

    application = FastAPI(title="HealthMindControl", version="0.2.0", lifespan=lifespan)
    application.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE / "templates")
    templates.env.globals.update(
        fmt_ts=ui_fmt.ts, fmt_iso=ui_fmt.ts_iso, col_label=ui_fmt.column_label,
        is_time_col=ui_fmt.is_time_column, badge_cls=ui_fmt.badge_class,
    )
    application.state.templates = templates
    for router in ROUTERS:
        application.include_router(router)
    return application


app = create_app()
