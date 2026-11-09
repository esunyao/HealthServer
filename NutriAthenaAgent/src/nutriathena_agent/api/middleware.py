"""Request diary without query strings, bearer values or response bodies."""
import re
import time
from typing import Any
from uuid import uuid4
from fastapi import Request
from ..logging_service import log_context, log_event, log_exception
_TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

def _request_trace_id(request: Request) -> str:
    for name in ('x-trace-id', 'x-request-id'):
        value = request.headers.get(name, '').strip()
        if value and _TRACE_ID_PATTERN.fullmatch(value):
            return value
    return uuid4().hex

def _status_level(status_code: int) -> str:
    if status_code >= 500:
        return 'ERROR'
    if status_code >= 400:
        return 'WARNING'
    return 'INFO'

async def log_request(request: Request, call_next: Any) -> Any:
    trace_id = _request_trace_id(request)
    path = request.url.path
    started = time.perf_counter()
    with log_context(trace_id=trace_id):
        log_event('http.request.started', level='DEBUG', method=request.method, path=path)
        try:
            response = await call_next(request)
        except Exception as exception:
            log_exception('http.request.failed', exception, method=request.method, path=path, duration_ms=int((time.perf_counter() - started) * 1000))
            raise
        level = 'DEBUG' if path == '/healthz' else _status_level(response.status_code)
        log_event('http.request.finished', level=level, method=request.method, path=path, status_code=response.status_code, duration_ms=int((time.perf_counter() - started) * 1000))
        response.headers['X-Request-Id'] = trace_id
        return response
