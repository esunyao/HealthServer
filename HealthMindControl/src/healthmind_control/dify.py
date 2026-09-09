import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from .config import Settings


class DifyService:
    def __init__(self, cfg: Settings):
        self.cfg = cfg

    async def probe(self, url: str, expected_401: bool = False) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                response = await client.get(url)
            ok = response.is_success or (expected_401 and response.status_code == 401 and "bearer" in response.headers.get("www-authenticate", "").lower())
            return {"ok": ok, "status": response.status_code}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def discover(self, app_id: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {}
        commands = {
            "workspaces": ["get", "workspace", "-o", "json"],
            "apps": ["get", "app", "-o", "json"],
        }
        if app_id:
            commands["app"] = ["describe", "app", app_id, "-o", "json"]
        for name, args in commands.items():
            try:
                proc = await asyncio.create_subprocess_exec(
                    self.cfg.difyctl_path, *args,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), 15)
                if proc.returncode:
                    result[name] = {"error": stderr.decode("utf-8", "replace")[-500:]}
                else:
                    result[name] = json.loads(stdout.decode("utf-8"))
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

