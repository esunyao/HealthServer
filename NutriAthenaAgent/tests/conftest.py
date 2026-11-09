from __future__ import annotations

import logging
from typing import Iterator

import pytest
from loguru import logger

from nutriathena_agent.observability import reset_logging

_LOGGER_NAMES = (
    "",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.asgi",
    "uvicorn.access",
    "httpx",
    "httpcore",
    "mcp",
    "openai",
    "langchain",
    "langchain_core",
    "langgraph",
    "psycopg",
    "psycopg_pool",
    "urllib3",
)


def _capture_logger_states() -> dict[str, tuple[list[logging.Handler], int, bool]]:
    states: dict[str, tuple[list[logging.Handler], int, bool]] = {}
    for name in _LOGGER_NAMES:
        target = logging.getLogger(name)
        states[name] = (list(target.handlers), target.level, target.propagate)
    return states


def _restore_logger_states(states: dict[str, tuple[list[logging.Handler], int, bool]]) -> None:
    for name, (handlers, level, propagate) in states.items():
        target = logging.getLogger(name)
        target.handlers = handlers
        target.setLevel(level)
        target.propagate = propagate


@pytest.fixture(autouse=True)
def _clean_logging() -> Iterator[None]:
    """Keep loguru and stdlib logging state isolated between tests."""
    reset_logging()
    saved = _capture_logger_states()
    logger.remove()
    logger.add(lambda _: None, format="{message}", level="DEBUG")
    try:
        yield
    finally:
        reset_logging()
        logger.remove()
        _restore_logger_states(saved)
