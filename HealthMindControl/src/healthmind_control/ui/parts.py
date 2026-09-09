from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
_templates: Jinja2Templates | None = None


def templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def _echo_params(params, keep: tuple[str, ...], cursor: str | None = None, limit: int = 50):
    query = {k: v for k, v in params.items() if k in keep and v}
    if cursor:
        query["cursor"] = cursor
    query["limit"] = limit
    return urlencode(query)


TASK_PARAMS = ("status", "task_type", "service", "code", "subject", "since", "until")
ROW_PARAMS = ("status", "analysis", "code", "service", "subject_id", "since", "until")


@router.get("/ui/parts/tasks")
async def parts_tasks(request: Request):
    repo = request.app.state.repo
    result = await repo.list_tasks(
        **{k: request.query_params.get(k) for k in TASK_PARAMS},
        cursor=request.query_params.get("cursor"),
        limit=min(int(request.query_params.get("limit", 50)), 100),
    )
    next_cursor = result["next_cursor"]
    return templates(request).TemplateResponse(
        request, "partials/task_table.html",
        {"rows": result["items"], "next_url": (
            "/ui/parts/tasks?" + _echo_params(request.query_params, TASK_PARAMS, next_cursor) if next_cursor else None
        )},
    )


@router.get("/ui/parts/rows")
async def parts_rows(request: Request, kind: str):
    repo = request.app.state.repo
    try:
        result = await repo.list_rows(
            kind,
            **{k: request.query_params.get(k) for k in ROW_PARAMS},
            cursor=request.query_params.get("cursor"),
            limit=min(int(request.query_params.get("limit", 50)), 100),
        )
    except KeyError:
        raise HTTPException(404, "unknown row kind")
    next_cursor = result["next_cursor"]
    from ..repositories.rows import get_kind
    return templates(request).TemplateResponse(
        request, "partials/row_table.html",
        {"kind": kind, "id_col": get_kind(kind).id_col, "rows": result["items"], "next_url": (
            "/ui/parts/rows?kind=" + kind + "&" + _echo_params(request.query_params, ROW_PARAMS, next_cursor) if next_cursor else None
        )},
    )
