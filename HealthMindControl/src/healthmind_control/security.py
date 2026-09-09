import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request


SENSITIVE = {
    "authorization", "token", "access_token", "refresh_token", "client_secret", "client_key",
    "password", "pwd", "passwd", "api_key", "apikey", "x-api-key", "secret", "secret_key",
    "private_key", "credential", "signature", "session_key", "accesskey", "access_key_id",
}

# URL 查询参数中出现这些标记即视为预签名/凭据链接，整体截断
URL_SIGNATURE_MARKERS = (
    "x-amz-signature=", "x-amz-credential=", "x-goog-signature=",
    "x-oss-signature=", "x-oss-", "signature=", "sig=",
    "osaccesskeyid", "credential=", "security-token=", "x-oss-security-token=",
)


def redact(value: Any) -> Any:
    """递归脱敏：敏感键值置 ***；带签名类查询参数的 URL 截断为 path + ?REDACTED。"""
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in SENSITIVE else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str) and "?" in value:
        query = value.split("?", 1)[1].lower()
        if any(marker in query for marker in URL_SIGNATURE_MARKERS):
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
    """单次使用的预览令牌仓库：绑定 action 与快照哈希，TTL 后失效。"""

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
