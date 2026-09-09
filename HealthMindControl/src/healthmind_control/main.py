import uvicorn

from .config import settings


def run() -> None:
    if settings.host != "127.0.0.1":
        raise SystemExit("HealthMindControl v1 only permits HMC_HOST=127.0.0.1")
    uvicorn.run("healthmind_control.app:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()

