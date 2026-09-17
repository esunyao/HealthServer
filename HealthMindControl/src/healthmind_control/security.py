import hashlib
import json
import secrets
import threading
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request


SENSITIVE = {
    "authorization", "token", "access_token", "refresh_token", "client_secret", "client_key",
    "password", "pwd", "passwd", "api_key", "apikey", "x-api-key", "secret", "secret_key",
    "private_key", "credential", "signature", "session_key", "accesskey", "access_key_id",
    "bearer", "app_api_key",
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
    operation_id: str
    state: str = "active"
    result: Any = None
    error: str | None = None


def control_error(
    status_code: int,
    code: str,
    message: str,
    *,
    can_retry: bool = False,
    requires_repreview: bool = False,
    operation_id: str | None = None,
) -> HTTPException:
    """Build the stable error envelope used by every controlled write endpoint."""
    return HTTPException(status_code, detail={
        "code": code,
        "message": message,
        "can_retry": can_retry,
        "requires_repreview": requires_repreview,
        "operation_id": operation_id,
    })


def replayed_result(result: Any) -> Any:
    """Return a cached successful result without changing its original fields."""
    cached = deepcopy(result)
    if isinstance(cached, dict):
        cached["replayed"] = True
        return cached
    return {"result": cached, "replayed": True}


class PreviewStore:
    """预览令牌状态机：预检可重试，副作用阶段只允许一个执行者。"""

    def __init__(self, ttl: int):
        self.ttl = ttl
        self._items: dict[str, Preview] = {}
        self._lock = threading.RLock()

    def create(self, action: str, payload: dict[str, Any], snapshot: Any) -> tuple[str, Preview]:
        with self._lock:
            self.prune()
            token = secrets.token_urlsafe(32)
            preview = Preview(
                action=action,
                payload=deepcopy(payload),
                snapshot_hash=sha256_json(snapshot),
                expires_at=time.time() + self.ttl,
                operation_id=str(uuid.uuid4()),
            )
            self._items[token] = preview
            return token, preview

    def inspect(self, token: str, action: str, *, prefix: bool = False) -> Preview:
        """Validate a token without occupying it; safe for correctable preflight checks."""
        with self._lock:
            preview = self._items.get(token)
            if preview is None or preview.expires_at < time.time():
                if preview is not None:
                    self._items.pop(token, None)
                raise control_error(
                    409, "PREVIEW_EXPIRED", "预览令牌无效或已过期，请重新预览",
                    requires_repreview=True,
                    operation_id=preview.operation_id if preview else None,
                )
            matches = preview.action.startswith(action) if prefix else preview.action == action
            if not matches:
                raise control_error(
                    409, "PREVIEW_TARGET_MISMATCH", "预览目标与执行操作不匹配",
                    requires_repreview=True, operation_id=preview.operation_id,
                )
            return preview

    def begin(self, token: str, action: str, *, prefix: bool = False) -> tuple[Preview, bool, Any]:
        """Atomically claim an active preview, or return its cached successful result."""
        with self._lock:
            preview = self.inspect(token, action, prefix=prefix)
            if preview.state == "succeeded":
                return preview, True, deepcopy(preview.result)
            if preview.state == "executing":
                raise control_error(
                    409, "PREVIEW_EXECUTING", "该操作正在执行，请勿重复提交",
                    can_retry=True, operation_id=preview.operation_id,
                )
            if preview.state == "indeterminate":
                raise control_error(
                    409, "EXECUTION_INDETERMINATE",
                    preview.error or "执行结果无法确认，请通过操作编号检查审计和目标记录",
                    operation_id=preview.operation_id,
                )
            preview.state = "executing"
            preview.error = None
            preview.expires_at = max(preview.expires_at, time.time() + self.ttl)
            return preview, False, None

    def replay(self, token: str, action: str, *, prefix: bool = False) -> tuple[Preview, bool, Any]:
        """Check terminal/in-flight state without occupying an active preview."""
        with self._lock:
            preview = self.inspect(token, action, prefix=prefix)
            if preview.state == "succeeded":
                return preview, True, deepcopy(preview.result)
            if preview.state == "executing":
                raise control_error(
                    409, "PREVIEW_EXECUTING", "该操作正在执行，请勿重复提交",
                    can_retry=True, operation_id=preview.operation_id,
                )
            if preview.state == "indeterminate":
                raise control_error(
                    409, "EXECUTION_INDETERMINATE",
                    preview.error or "执行结果无法确认，请通过操作编号检查审计和目标记录",
                    operation_id=preview.operation_id,
                )
            return preview, False, None

    def succeed(self, token: str, result: Any) -> None:
        with self._lock:
            preview = self._items.get(token)
            if preview is None:
                return
            preview.state = "succeeded"
            preview.result = deepcopy(result)
            preview.error = None
            preview.expires_at = time.time() + self.ttl

    def release(self, token: str, error: str | None = None) -> None:
        """Return an occupied token to active only when no side effect was started."""
        with self._lock:
            preview = self._items.get(token)
            if preview is not None and preview.state == "executing":
                preview.state = "active"
                preview.error = error

    def indeterminate(self, token: str, error: str) -> None:
        with self._lock:
            preview = self._items.get(token)
            if preview is not None:
                preview.state = "indeterminate"
                preview.error = error
                preview.expires_at = time.time() + self.ttl

    def consume(self, token: str, action: str) -> Preview:
        """Compatibility shim. New endpoints must use inspect/begin/succeed explicitly."""
        preview, replayed, _ = self.begin(token, action)
        if replayed:
            raise control_error(
                409, "PREVIEW_ALREADY_SUCCEEDED", "该操作已经成功执行",
                operation_id=preview.operation_id,
            )
        return preview

    def consume_for_prefix(self, token: str, action_prefix: str) -> Preview:
        preview, replayed, _ = self.begin(token, action_prefix, prefix=True)
        if replayed:
            raise control_error(
                409, "PREVIEW_ALREADY_SUCCEEDED", "该操作已经成功执行",
                operation_id=preview.operation_id,
            )
        return preview

    def prune(self) -> None:
        with self._lock:
            now = time.time()
            self._items = {k: v for k, v in self._items.items() if v.expires_at >= now}


def require_csrf(request: Request, token: str | None) -> None:
    expected = request.app.state.csrf_token
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(403, "CSRF token invalid")


def require_database_available(request: Request) -> None:
    db = request.app.state.db
    if not getattr(db, "connected", False):
        raise control_error(
            503, "DEPENDENCY_UNAVAILABLE",
            db.schema_error or "数据库暂不可用，后台正在自动重连",
            can_retry=True,
        )


def write_started_audit(
    request: Request,
    preview_token: str,
    action: str,
    target: str,
    reason: str,
    operation_id: str,
    **details: Any,
) -> None:
    """Persist the mandatory start audit before side effects, releasing on local I/O failure."""
    try:
        request.app.state.audit.write(
            action, target, reason, "started", operation_id=operation_id, **details,
        )
    except Exception as exc:
        request.app.state.previews.release(preview_token, str(exc))
        raise control_error(
            503, "DEPENDENCY_UNAVAILABLE", f"审计日志暂不可写: {exc}",
            can_retry=True, operation_id=operation_id,
        ) from exc


def write_failed_audit(
    request: Request,
    action: str,
    target: str,
    reason: str,
    operation_id: str,
    error: Exception | str,
) -> None:
    """Best-effort terminal audit; never hide the original execution uncertainty."""
    try:
        request.app.state.audit.write(
            action, target, reason, "failed", operation_id=operation_id, error=str(error),
        )
    except Exception:
        pass
