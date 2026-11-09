"""Build the HTTP adapter around explicitly composed runtime resources."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..config import RuntimeSettings
from ..execution.ports import MealRunner, RunRepository, TokenVerifier
from ..execution.types import RunServiceError
from ..runtime.bootstrap import build_runtime
from ..runtime.lifecycle import lifespan
from .middleware import log_request
from .routes import health, thread, run


def create_app(
    *,
    settings: RuntimeSettings | None = None,
    repository: RunRepository | None = None,
    runner: MealRunner | None = None,
    token_verifier: TokenVerifier | None = None,
    start_worker: bool = True,
    artifact_sha256: str | None = None,
) -> FastAPI:
    resources = build_runtime(
        settings=settings,
        repository=repository,
        runner=runner,
        token_verifier=token_verifier,
        start_worker=start_worker,
        artifact_sha256=artifact_sha256,
    )
    app = FastAPI(title="NutriAthenaAgent", version="1.0", lifespan=lifespan)
    app.state.runtime = resources
    app.state.settings = resources.settings
    app.state.repository = resources.repository
    app.state.token_verifier = resources.token_verifier
    app.state.artifact_sha256 = resources.identity.artifact_sha256
    app.state.worker = resources.worker
    app.state.health_failure_logged = False
    app.middleware("http")(log_request)

    @app.exception_handler(RunServiceError)
    async def run_error(_: Request, error: RunServiceError):
        return JSONResponse(
            status_code=error.status_code, content={"detail": error.detail}
        )

    for router in (health.router, thread.router, run.router):
        app.include_router(router)
    return app
