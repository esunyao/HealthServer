from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()

VIEWS = ("dashboard", "tasks", "rows", "trace", "kafka", "releases", "repair", "audit", "about")
VIEW_TITLES = {
    "dashboard": "运行总览", "tasks": "AI 任务", "rows": "数据浏览", "trace": "链路追踪",
    "kafka": "Kafka 管理", "releases": "Dify 版本", "repair": "受控修复",
    "audit": "审计记录", "about": "关于",
}


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse("/ui/dashboard")


@router.get("/ui/{view}", response_class=HTMLResponse)
async def view_page(request: Request, view: str):
    if view not in VIEWS:
        raise HTTPException(404, "unknown view")
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        f"views/{view}.html",
        {
            "view": view,
            "title": VIEW_TITLES[view],
            "csrf_token": request.app.state.csrf_token,
            "refresh": request.app.state.refresh_seconds,
        },
    )
