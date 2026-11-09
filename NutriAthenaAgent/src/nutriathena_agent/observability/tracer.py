"""Opt-in debug events and content using the common logging pipeline."""

from __future__ import annotations

from typing import Any

from .levels import DebugLevel, parse_debug_level
from .logging import configure_logging, log_event


def configure_debug_logging(level: DebugLevel) -> None:
    """Backward-compatible wrapper around the unified logging service."""
    configure_logging(level)


class DebugTracer:
    def __init__(
        self,
        level: DebugLevel | str,
        *,
        trace_id: str = "",
        run_id: str = "",
        logger: Any = None,
    ) -> None:
        self.level = parse_debug_level(level)
        self.trace_id = trace_id
        self.run_id = run_id
        self._logger = logger

    @property
    def enabled(self) -> bool:
        return self.level is not DebugLevel.OFF

    @property
    def full(self) -> bool:
        return self.level is DebugLevel.FULL

    def event(self, name: str, **fields: Any) -> None:
        if not self.enabled:
            return
        try:
            log_event(
                name,
                level="DEBUG",
                trace_id=self.trace_id or None,
                run_id=self.run_id or None,
                **fields,
            )
        except Exception:
            # Tracing must never fail the agent run.
            pass

    def content(self, label: str, text: str) -> None:
        if not self.full:
            return
        try:
            log_event("content", level="DEBUG", label=label, text=str(text))
        except Exception:
            pass


