import json
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from jsonschema import Draft202012Validator, SchemaError

from ..models import BindToolsRequest, ExecuteRequest, ReleaseRequest
from ..security import (
    control_error, redact, replayed_result, require_csrf, require_database_available, sha256_json,
    write_failed_audit, write_started_audit,
)
from ..util import serial

router = APIRouter()


def _require_release_writes(request: Request, operation_id: str | None = None) -> None:
    if not getattr(request.app.state.db, "connected", True):
        raise control_error(503, "DEPENDENCY_UNAVAILABLE",
                            request.app.state.db.schema_error or "数据库暂不可用，后台正在自动重连",
                            can_retry=True, operation_id=operation_id)
    if not request.app.state.db.write_features.get("releases"):
        raise control_error(409, "WRITE_DISABLED",
                            request.app.state.db.schema_error or "release writes are disabled",
                            operation_id=operation_id)


def _release_snapshot(body: ReleaseRequest) -> dict[str, Any]:
    return {
        "operation": body.operation, "release_id": body.release_id,
        "workflow_id": body.workflow_id, "workflow_version": body.workflow_version,
        "release_version": body.release_version,
    }


# ---------------------------------------------------------------- 查询
@router.get("/api/releases")
async def releases(request: Request):
    require_database_available(request)
    return serial(await request.app.state.repo.list_releases())


@router.get("/api/releases/{release_id}")
async def release_detail(request: Request, release_id: str):
    require_database_available(request)
    row = await request.app.state.repo.release_detail(release_id)
    if not row:
        raise HTTPException(404, "release not found")
    return serial(redact(row))


@router.get("/api/releases/{release_id}/audits")
async def release_audits(request: Request, release_id: str, limit: int = 200):
    require_database_available(request)
    return serial(await request.app.state.repo.release_audits(release_id, limit))


@router.get("/api/audits/releases")
async def all_release_audits(request: Request, limit: int = 200):
    require_database_available(request)
    return serial(await request.app.state.repo.release_audits(None, limit))


@router.get("/api/dify/tool-definitions")
async def tool_definitions(request: Request):
    require_database_available(request)
    return serial(await request.app.state.repo.tool_definitions())


# ---------------------------------------------------------------- difyctl 探测与解析
@router.get("/api/dify/discover")
async def dify_discover(request: Request, app_id: str | None = None, with_dsl: bool = False):
    return await request.app.state.dify.discover(app_id, with_dsl)


@router.post("/api/dify/analyze")
async def dify_analyze(request: Request):
    """解析用户粘贴文本：workflows/publish JSON 或 studio DSL（YAML/JSON），尽力提取字段。"""
    body = await request.json()
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(422, "empty text")
    proposal: dict[str, Any] = {"hints": [], "fields": {}}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = yaml.safe_load(text)
            proposal["hints"].append("按 DSL(YAML) 解析")
        except yaml.YAMLError:
            raise HTTPException(422, "无法解析为 JSON 或 YAML")
    if isinstance(data, dict):
        publish = data.get("data") if isinstance(data.get("data"), dict) else data
        workflow = publish.get("workflow") if isinstance(publish, dict) else None
        if isinstance(workflow, dict):
            proposal["fields"]["workflow_id"] = workflow.get("id") or workflow.get("workflow_id")
            proposal["fields"]["workflow_version"] = workflow.get("version") or workflow.get("updated_at") or workflow.get("created_at")
        app_node = (publish or {}).get("app") or (data.get("app") if isinstance(data.get("app"), dict) else None)
        if isinstance(app_node, dict):
            proposal["fields"]["app_id"] = app_node.get("id") or app_node.get("app_id")
            if app_node.get("name"):
                proposal["fields"]["app_name"] = app_node["name"]
        if proposal["fields"].get("workflow_version") is None and isinstance(publish, dict):
            proposal["fields"]["workflow_version"] = publish.get("updated_at") or publish.get("version")
        if isinstance(publish, dict) and proposal["fields"].get("workflow_id") is None:
            proposal["fields"]["workflow_id"] = publish.get("workflow_id") or publish.get("id")
        if isinstance(data, dict) and "workflow" in data and isinstance(data["workflow"], dict):
            proposal["hints"].append("DSL 只含草稿定义；published workflow id/version 请以 workflows/publish 返回为准")
        # 输入表单 → schema 草案
        features = None
        workflow_node = data.get("workflow") if isinstance(data, dict) else None
        if isinstance(workflow_node, dict):
            features = workflow_node.get("features")
        if isinstance(features, dict) and isinstance(features.get("user_input_form"), list):
            properties, required = {}, []
            for item in features["user_input_form"]:
                if not isinstance(item, dict):
                    continue
                form = next(iter(item.values())) if item else None
                if not isinstance(form, dict):
                    continue
                variable = form.get("variable")
                if not variable:
                    continue
                ftype = form.get("type")
                properties[variable] = {
                    "type": {"number": "number", "paragraph": "string", "file": "string", "select": "string", "text-input": "string"}.get(ftype, "string"),
                    "description": form.get("label") or form.get("placeholder"),
                }
                if form.get("required"):
                    required.append(variable)
            if properties:
                schema = {"type": "object", "additionalProperties": False,
                          "required": required, "properties": properties}
                proposal["fields"]["input_schema"] = schema
                proposal["hints"].append("input schema 由 DSL user_input_form 自动生成，属于信封内 payload 草案，请人工核对")
    return serial(proposal)


# ---------------------------------------------------------------- 版本向导（预览 + 执行）
@router.post("/api/releases/preview")
async def release_preview(request: Request, body: ReleaseRequest):
    require_csrf(request, body.csrf_token)
    if body.operation == "create":
        required = [body.release_version, body.workspace_id, body.app_id, body.workflow_id,
                    body.workflow_version, body.input_schema, body.output_schema]
        if any(v is None for v in required):
            raise HTTPException(422, "create requires all Dify IDs, version and schemas")
        if not body.tool_codes:
            raise HTTPException(422, "create requires at least one MCP tool binding")
        try:
            Draft202012Validator.check_schema(body.input_schema)
            Draft202012Validator.check_schema(body.output_schema)
        except SchemaError as exc:
            raise HTTPException(422, f"invalid JSON schema: {exc.message}")
        snapshot = _release_snapshot(body)
    else:
        if not body.release_id:
            raise HTTPException(422, "release_id required")
        snapshot = await request.app.state.repo.snapshot("healthmind.workflow_releases", "release_id", body.release_id)
        if not snapshot:
            raise HTTPException(404, "release not found")
    token, preview = request.app.state.previews.create(
        "release." + body.operation, body.model_dump(exclude={"preview_token"}), snapshot,
    )
    return {
        "preview_token": token, "expires_at": preview.expires_at, "operation_id": preview.operation_id,
        "snapshot": serial(redact(snapshot)), "confirmation": f"RELEASE {body.operation.upper()}",
    }


@router.post("/api/releases/execute")
async def release_execute(request: Request, body: ExecuteRequest):
    require_csrf(request, body.csrf_token)
    preview = request.app.state.previews.inspect(body.preview_token, "release.", prefix=True)
    intent = ReleaseRequest.model_validate(preview.payload)
    if body.confirmation != f"RELEASE {intent.operation.upper()}":
        raise control_error(409, "CONFIRMATION_MISMATCH", "确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(body.preview_token, "release.", prefix=True)
    if replayed:
        return replayed_result(cached)
    _require_release_writes(request, preview.operation_id)
    if intent.operation != "create":
        current = await request.app.state.repo.snapshot("healthmind.workflow_releases", "release_id", intent.release_id or "")
        if not current or sha256_json(current) != preview.snapshot_hash:
            raise control_error(409, "PREVIEW_STALE", "版本在预览后发生变化，请重新预览",
                                requires_repreview=True, operation_id=preview.operation_id)
    before = None if intent.operation == "create" else current
    preview, replayed, cached = request.app.state.previews.begin(body.preview_token, "release.", prefix=True)
    if replayed:
        return replayed_result(cached)
    op = preview.operation_id
    write_started_audit(
        request, body.preview_token, "release." + intent.operation,
        intent.release_id or intent.release_version or "new", intent.reason, op,
        before=redact(before),
    )
    try:
        if intent.operation == "create":
            rid = await request.app.state.repo.create_release(intent.model_dump(), intent.reason)
        else:
            rid = intent.release_id
            await request.app.state.repo.transition_release(rid, intent.operation, intent.reason)
        after = await request.app.state.repo.release_detail(str(rid))
        request.app.state.audit.write("release." + intent.operation, rid, intent.reason, "succeeded", operation_id=op,
                                      before=redact(before), after=redact(after))
        result = {"release_id": rid, "status": "ok"}
        request.app.state.previews.succeed(body.preview_token, result)
        return result
    except Exception as exc:
        write_failed_audit(request, "release." + intent.operation,
                           intent.release_id or "new", intent.reason, op, exc)
        request.app.state.previews.indeterminate(body.preview_token, str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "版本变更结果无法确认，请通过操作编号检查审计和版本记录",
                            operation_id=op) from exc


# ---------------------------------------------------------------- 候选绑定工具（预览 + 执行）
@router.post("/api/releases/{release_id}/tools/preview")
async def bind_tools_preview(request: Request, release_id: str, body: BindToolsRequest):
    require_csrf(request, body.csrf_token)
    detail = await request.app.state.repo.release_detail(release_id)
    if not detail:
        raise HTTPException(404, "release not found")
    if detail["status"] != "candidate":
        raise HTTPException(409, "仅 candidate 版本允许修改工具绑定")
    snapshot = {"release_id": release_id, "status": detail["status"], "bound": [t.get("tool_code") for t in detail["tools"]]}
    token, preview = request.app.state.previews.create(
        "release.bind_tools", body.model_dump(exclude={"preview_token"}), snapshot,
    )
    return {
        "preview_token": token, "expires_at": preview.expires_at, "operation_id": preview.operation_id,
        "snapshot": serial(snapshot), "confirmation": "RELEASE BIND_TOOLS",
    }


@router.post("/api/releases/{release_id}/tools/execute")
async def bind_tools_execute(request: Request, release_id: str, body: ExecuteRequest):
    require_csrf(request, body.csrf_token)
    token = body.preview_token or ""
    preview = request.app.state.previews.inspect(token, "release.bind_tools")
    intent = BindToolsRequest.model_validate(preview.payload)
    if intent.release_id != release_id:
        raise control_error(409, "PREVIEW_TARGET_MISMATCH", "预览目标不匹配",
                            requires_repreview=True, operation_id=preview.operation_id)
    if body.confirmation != "RELEASE BIND_TOOLS":
        raise control_error(409, "CONFIRMATION_MISMATCH", "确认文本不匹配", can_retry=True,
                            operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.replay(token, "release.bind_tools")
    if replayed:
        return serial(replayed_result(cached))
    _require_release_writes(request, preview.operation_id)
    current = await request.app.state.repo.release_detail(release_id)
    snapshot = {"release_id": release_id, "status": current["status"] if current else None,
                "bound": [t.get("tool_code") for t in current["tools"]] if current else []}
    if not current or sha256_json(snapshot) != preview.snapshot_hash:
        raise control_error(409, "PREVIEW_STALE", "版本在预览后发生变化，请重新预览",
                            requires_repreview=True, operation_id=preview.operation_id)
    preview, replayed, cached = request.app.state.previews.begin(token, "release.bind_tools")
    if replayed:
        return serial(replayed_result(cached))
    op = preview.operation_id
    write_started_audit(request, token, "release.bind_tools", release_id, intent.reason, op)
    try:
        result = await request.app.state.repo.bind_tools(
            release_id, [b.model_dump() for b in intent.bindings], intent.reason,
        )
        request.app.state.audit.write("release.bind_tools", release_id, intent.reason, "succeeded", operation_id=op)
        final = serial(result)
        request.app.state.previews.succeed(token, final)
        return final
    except Exception as exc:
        write_failed_audit(request, "release.bind_tools", release_id, intent.reason, op, exc)
        request.app.state.previews.indeterminate(token, str(exc))
        raise control_error(503, "EXECUTION_INDETERMINATE",
                            "工具绑定结果无法确认，请通过操作编号检查审计和版本记录",
                            operation_id=op) from exc
