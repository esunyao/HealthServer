import asyncio
import json
import re
import subprocess
import time
from typing import Any

import httpx

from ..config import Settings


def _safe_cli_error(value: str) -> str:
    """Limit CLI diagnostics and remove bearer/device-flow credentials."""
    value = re.sub(r"(?i)\b(Bearer\s+)\S+", r"\1***", value)
    value = re.sub(r"\bdfo[ae]_[A-Za-z0-9._~-]+", "***", value)
    return value[-500:]


class DifyService:
    """Dify 探活与 difyctl 探测（工作区/应用/DSL），探活带 TTL 缓存。"""

    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self._probe_cache: dict[str, dict[str, Any]] = {}
        self.client = httpx.AsyncClient(timeout=10, follow_redirects=True)

    async def close(self) -> None:
        await self.client.aclose()

    async def probe(self, url: str, expected_401: bool = False, auth_ok: bool = False) -> dict[str, Any]:
        """可达性探活（不带凭据）。

        - expected_401: Dify /v1/info 语义——401 + Bearer challenge 视为可达；
        - auth_ok: 端点处于认证网关之后——401/403/405/429（服务器已应答）视为可达。
        """
        now = time.monotonic()
        cached = self._probe_cache.get(url)
        if cached and now - cached["at"] < self.cfg.probe_cache_ttl_seconds:
            return cached["value"]
        try:
            response = await self.client.get(url, timeout=5)
            status = response.status_code
            ok = response.is_success or (
                expected_401 and status == 401
                and "bearer" in response.headers.get("www-authenticate", "").lower()
            ) or (auth_ok and status in (401, 403, 405, 429))
            value = {"ok": ok, "status": status}
        except Exception as exc:
            value = {"ok": False, "error": str(exc)}
        self._probe_cache[url] = {"at": now, "value": value}
        return value

    async def _run_difyctl(self, args: list[str], timeout: float = 20) -> tuple[int, str]:
        def run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [self.cfg.difyctl_path, *args], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout, check=False,
            )
        completed = await asyncio.to_thread(run)
        return completed.returncode, completed.stdout or completed.stderr

    async def discover(self, app_id: str | None = None, with_dsl: bool = False) -> dict[str, Any]:
        """通过 difyctl 的 OAuth 会话探测应用；从不读取或返回凭据。"""
        result: dict[str, Any] = {
            "authenticated": False,
            "account": None,
            "version": None,
            "compatibility_warning": None,
            "workspace": None,
            "apps": [],
            "app": None,
            "dsl": None,
            "resolved": {},
            "errors": {},
        }

        async def json_command(name: str, args: list[str]) -> dict[str, Any] | None:
            try:
                code, text = await self._run_difyctl(args)
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                result["errors"][name] = _safe_cli_error(str(exc))
                return None
            except Exception as exc:
                result["errors"][name] = _safe_cli_error(str(exc))
                return None
            if code:
                result["errors"][name] = _safe_cli_error(text) or f"exit code {code}"
                return None
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                result["errors"][name] = "difyctl 未返回有效 JSON"
                return None
            return value if isinstance(value, dict) else {"data": value}

        version = await json_command("version", ["version", "-o", "json"])
        if version:
            result["version"] = version
            compat = version.get("compat")
            if isinstance(compat, dict) and compat.get("status") not in (None, "compatible", "ok"):
                result["compatibility_warning"] = compat.get("detail") or str(compat.get("status"))

        account = await json_command("auth", ["auth", "whoami", "--json"])
        if not account:
            result["login_hint"] = "请先在终端运行 difyctl auth login"
            return result
        result["authenticated"] = True
        result["account"] = account

        workspace_payload = await json_command("workspaces", ["get", "workspace", "-o", "json"])
        workspaces = workspace_payload.get("workspaces", []) if workspace_payload else []
        if isinstance(workspaces, list) and workspaces:
            current = next((item for item in workspaces if item.get("current")), workspaces[0])
            result["workspace"] = current
            result["resolved"]["workspace_id"] = current.get("id")

        apps_payload = await json_command("apps", ["get", "app", "-o", "json"])
        apps = apps_payload.get("data", []) if apps_payload else []
        if isinstance(apps, list):
            result["apps"] = apps

        if not app_id:
            return result

        app = await json_command("app", ["describe", "app", app_id, "-o", "json", "--refresh"])
        if app:
            result["app"] = app
            info = app.get("info") if isinstance(app.get("info"), dict) else {}
            result["resolved"]["app_id"] = info.get("id") or app_id
            if isinstance(app.get("input_schema"), dict):
                result["resolved"]["dify_input_schema"] = app["input_schema"]

        if with_dsl:
            try:
                # --output/-o 是文件路径，不是格式；省略后 DSL 才会输出到 stdout。
                code, text = await self._run_difyctl(["export", "studio-app", app_id])
                if code:
                    result["errors"]["dsl"] = _safe_cli_error(text) or f"exit code {code}"
                else:
                    result["dsl"] = {"yaml": text}
            except Exception as exc:
                result["errors"]["dsl"] = _safe_cli_error(str(exc))
        return result
