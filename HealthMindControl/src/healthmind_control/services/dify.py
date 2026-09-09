import asyncio
import json
import time
from typing import Any

import httpx

from ..config import Settings


class DifyService:
    """Dify 探活与 difyctl 探测（工作区/应用/DSL），探活带 TTL 缓存。"""

    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self._probe_cache: dict[str, dict[str, Any]] = {}

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
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                response = await client.get(url)
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
        proc = await asyncio.create_subprocess_exec(
            self.cfg.difyctl_path, *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        return proc.returncode, (stdout or b"").decode("utf-8", "replace")

    async def discover(self, app_id: str | None = None, with_dsl: bool = False) -> dict[str, Any]:
        """探测序列：workspaces → apps →（可选）describe app →（可选）export studio-app DSL。"""
        result: dict[str, Any] = {}
        commands = {"workspaces": ["get", "workspace", "-o", "json"], "apps": ["get", "app", "-o", "json"]}
        if app_id:
            commands["app"] = ["describe", "app", app_id, "-o", "json"]
            if with_dsl:
                commands["dsl"] = ["export", "studio-app", app_id, "-o", "yaml"]
        for name, args in commands.items():
            try:
                code, text = await self._run_difyctl(args)
                if code:
                    result[name] = {"error": text[-500:] or f"exit code {code}"}
                    continue
                if name == "dsl":
                    result[name] = {"yaml": text}
                else:
                    try:
                        result[name] = json.loads(text)
                    except json.JSONDecodeError:
                        result[name] = {"raw": text[:2000]}
            except Exception as exc:
                result[name] = {"error": str(exc)}
        return result

    async def published(self, app_id: str) -> dict[str, Any]:
        if not self.cfg.dify_console_token:
            raise RuntimeError("未配置 HMC_DIFY_CONSOLE_TOKEN；请粘贴 workflows/publish JSON")
        url = f"{self.cfg.dify_url.rstrip('/')}/console/api/apps/{app_id}/workflows/publish"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {self.cfg.dify_console_token}"})
            response.raise_for_status()
            return response.json()
