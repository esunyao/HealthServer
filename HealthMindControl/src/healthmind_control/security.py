import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request


SENSITIVE = {"authorization", "token", "access_token", "client_secret", "password", "api_key"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in SENSITIVE else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str) and ("X-Amz-Signature=" in value or "x-oss-signature=" in value.lower()):
        return value.split("?", 1)[0] + "?REDACTED"
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


@dataclass
class Preview:
    action: str
    payload: dict[str, Any]
    snapshot_hash: str
    expires_at: float


class PreviewStore:
    def __init__(self, ttl: int):
        self.ttl = ttl
        self._items: dict[str, Preview] = {}

    def create(self, action: str, payload: dict[str, Any], snapshot: Any) -> tuple[str, Preview]:
        self.prune()
        token = secrets.token_urlsafe(32)
        preview = Preview(action, payload, sha256_json(snapshot), time.time() + self.ttl)
        self._items[token] = preview
        return token, preview

    def consume(self, token: str, action: str) -> Preview:
        preview = self._items.pop(token, None)
        if preview is None or preview.expires_at < time.time() or preview.action != action:
            raise HTTPException(409, "预览令牌无效或已过期，请重新预览")
        return preview

    def prune(self) -> None:
        now = time.time()
        self._items = {k: v for k, v in self._items.items() if v.expires_at >= now}


def require_csrf(request: Request, token: str | None) -> None:
    expected = request.app.state.csrf_token
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(403, "CSRF token invalid")
