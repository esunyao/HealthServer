import asyncio
import sys

import uvicorn

from .config import settings


def run() -> None:
    missing = settings.missing_external_envs()
    if missing:
        raise SystemExit("Missing required environment variables: " + ", ".join(missing))
    if settings.host != "127.0.0.1":
        raise SystemExit("HealthMindControl v1 only permits HMC_HOST=127.0.0.1")
    # psycopg async connections require a selector loop on Windows.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else "auto"
    uvicorn.run(
        "healthmind_control.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        loop=loop_factory,
    )


if __name__ == "__main__":
    run()
