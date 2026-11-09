"""Safe chained/aggregate exception rendering and Pydantic validation summaries."""

from __future__ import annotations

import traceback
from typing import Any, Iterator

from .redaction import redact_text, truncate

_MAX_EXCEPTION_CHARS = 64 * 1024
_MAX_VALIDATION_ERRORS = 20

def _iter_exception_chain(exception: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    stack: list[BaseException] = [exception]
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        nested = getattr(current, "exceptions", None)
        if isinstance(nested, (list, tuple)):
            stack.extend(item for item in nested if isinstance(item, BaseException))
        if current.__cause__ is not None:
            stack.append(current.__cause__)
        if current.__context__ is not None:
            stack.append(current.__context__)


def _is_validation_error(exception: BaseException) -> bool:
    return type(exception).__name__ == "ValidationError" and callable(getattr(exception, "errors", None))


def _validation_errors(exception: BaseException) -> list[dict[str, str]]:
    try:
        errors = exception.errors(  # type: ignore[attr-defined]
            include_input=False,
            include_url=False,
            include_context=False,
        )
    except TypeError:
        try:
            errors = exception.errors(include_input=False, include_url=False)  # type: ignore[attr-defined]
        except Exception:
            return []
    except Exception:
        return []
    if not isinstance(errors, list):
        return []
    summary: list[dict[str, str]] = []
    for item in errors[:_MAX_VALIDATION_ERRORS]:
        if not isinstance(item, dict):
            continue
        location = item.get("loc") or ()
        summary.append(
            {
                "loc": ".".join(str(part) for part in location),
                "type": str(item.get("type", "unknown")),
            }
        )
    return summary


def render_exception(
    exception: BaseException,
    *,
    content: bool,
) -> tuple[str, list[dict[str, str]] | None, str, int]:
    """Render an exception chain without leaking validation inputs.

    Returns ``(exception_text, validation_errors, error_chain, error_count)``.
    """
    chain = list(_iter_exception_chain(exception))
    error_chain = " <- ".join(type(item).__name__ for item in chain)
    validation = next((item for item in chain if _is_validation_error(item)), None)
    if validation is not None and not content:
        errors = _validation_errors(validation)
        total = len(errors)
        text = f"{error_chain}: {total} validation error(s)"
        return text, errors, error_chain, total
    try:
        text = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    except Exception:
        text = f"{type(exception).__name__}: {exception}"
    text = truncate(redact_text(text, content=content), _MAX_EXCEPTION_CHARS)
    return text, None, error_chain, 0


