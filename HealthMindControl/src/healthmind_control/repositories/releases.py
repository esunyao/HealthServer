from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from psycopg.types.json import Jsonb

from ..security import sha256_json


class ReleasesMixin:
    """Workflow 版本：轻量列表/详情/审计 + 创建/绑定工具/状态迁移。"""

    async def list_releases(self) -> list[dict[str, Any]]:
        """轻量列表（不带 schema 大 JSONB），含绑定工具与哈希。"""
        return await self.db.fetch_all("""
            SELECT wr.release_id, wr.task_type_id, wr.release_version, wr.status,
                   wr.dify_workspace_id, wr.dify_app_id, wr.dify_workflow_id, wr.dify_workflow_version,
                   wr.input_schema_version, wr.input_schema_sha256,
                   wr.output_schema_version, wr.output_schema_sha256,
                   wr.timeout_seconds, wr.max_attempts, wr.promoted_at, wr.retired_at, wr.created_at,
                   tt.task_type_code,
                   COALESCE(jsonb_agg(jsonb_build_object(
                       'tool_code', td.tool_code, 'display_name', td.display_name,
                       'owner_service', td.owner_service, 'scope', rt.allowed_scope,
                       'required', rt.required, 'max_calls', rt.max_calls, 'timeout_ms', rt.timeout_ms,
                       'request_schema_sha256', td.request_schema_sha256,
                       'response_schema_sha256', td.response_schema_sha256)
                     ) FILTER (WHERE td.tool_id IS NOT NULL), '[]'::jsonb) AS tools
              FROM healthmind.workflow_releases wr
              JOIN healthmind.ai_task_types tt USING (task_type_id)
              LEFT JOIN healthmind.workflow_release_tools rt USING (release_id)
              LEFT JOIN healthmind.ai_tool_definitions td USING (tool_id)
             GROUP BY wr.release_id, tt.task_type_code
             ORDER BY wr.created_at DESC
        """)

    async def release_detail(self, release_id: str) -> dict[str, Any] | None:
        row = await self.db.fetch_one("""
            SELECT wr.*, tt.task_type_code,
                   COALESCE(jsonb_agg(jsonb_build_object(
                       'tool_code', td.tool_code, 'display_name', td.display_name, 'description', td.description,
                       'owner_service', td.owner_service, 'operation_id', td.operation_id,
                       'scope', rt.allowed_scope, 'required', rt.required, 'max_calls', rt.max_calls,
                       'timeout_ms', rt.timeout_ms,
                       'request_schema_version', td.request_schema_version,
                       'request_schema_sha256', td.request_schema_sha256,
                       'response_schema_version', td.response_schema_version,
                       'response_schema_sha256', td.response_schema_sha256)
                     ) FILTER (WHERE td.tool_id IS NOT NULL), '[]'::jsonb) AS tools
              FROM healthmind.workflow_releases wr
              JOIN healthmind.ai_task_types tt USING (task_type_id)
              LEFT JOIN healthmind.workflow_release_tools rt USING (release_id)
              LEFT JOIN healthmind.ai_tool_definitions td USING (tool_id)
             WHERE wr.release_id = %s
             GROUP BY wr.release_id, tt.task_type_code
        """, (release_id,))
        return row

    async def release_audits(self, release_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        if release_id:
            return await self.db.fetch_all("""
                SELECT a.*, wr.release_version FROM healthmind.workflow_release_audits a
                JOIN healthmind.workflow_releases wr USING (release_id)
                WHERE a.release_id = %s ORDER BY a.occurred_at DESC LIMIT %s
            """, (release_id, min(limit, 500)))
        return await self.db.fetch_all("""
            SELECT a.*, wr.release_version FROM healthmind.workflow_release_audits a
            JOIN healthmind.workflow_releases wr USING (release_id)
            ORDER BY a.occurred_at DESC LIMIT %s
        """, (min(limit, 500),))

    async def tool_definitions(self) -> list[dict[str, Any]]:
        return await self.db.fetch_all("""
            SELECT tool_id, tool_code, display_name, description, owner_service, operation_id, auth_scope,
                   request_schema_version, request_schema_sha256, response_schema_version, response_schema_sha256
              FROM healthmind.ai_tool_definitions WHERE active ORDER BY tool_code
        """)

    async def create_release(self, data: dict[str, Any], reason: str) -> str:
        identity = "/".join(str(data[k]) for k in ("workspace_id", "app_id", "workflow_id", "workflow_version"))
        rid = str(uuid5(NAMESPACE_URL, identity))
        async with self.db.transaction() as conn:
            cur = await conn.execute(
                "SELECT task_type_id FROM healthmind.ai_task_types WHERE task_type_code=%s AND active",
                (data["task_type_code"],),
            )
            tt = await cur.fetchone()
            if not tt:
                raise RuntimeError("active task type not found")
            await conn.execute("""INSERT INTO healthmind.workflow_releases
              (release_id, task_type_id, release_version, status, dify_workspace_id, dify_app_id,
               dify_workflow_id, dify_workflow_version, input_schema_version, input_schema, input_schema_sha256,
               output_schema_version, output_schema, output_schema_sha256, timeout_seconds, max_attempts)
              VALUES (%s, %s, %s, 'candidate', %s, %s, %s, %s, '1.0', %s, %s, '1.0', %s, %s, 120, 1)""",
              (rid, tt["task_type_id"], data["release_version"], data["workspace_id"], data["app_id"],
               data["workflow_id"], data["workflow_version"],
               Jsonb(data["input_schema"]), sha256_json(data["input_schema"]),
               Jsonb(data["output_schema"]), sha256_json(data["output_schema"])))
            cur = await conn.execute(
                "SELECT tool_id, auth_scope FROM healthmind.ai_tool_definitions WHERE active AND tool_code = ANY(%s)",
                (data["tool_codes"],),
            )
            tools = await cur.fetchall()
            if len(tools) != len(data["tool_codes"]):
                raise RuntimeError("one or more active tool definitions are missing")
            for tool in tools:
                await conn.execute(
                    "INSERT INTO healthmind.workflow_release_tools(release_id, tool_id, allowed_scope, required, max_calls, timeout_ms)"
                    " VALUES (%s, %s, %s, true, 1, 10000)",
                    (rid, tool["tool_id"], tool["auth_scope"]),
                )
            await conn.execute(
                "INSERT INTO healthmind.workflow_release_audits(audit_id, release_id, action, to_status, reason)"
                " VALUES (%s, %s, 'created', 'candidate', %s)",
                (uuid4(), rid, reason),
            )
        return rid

    async def bind_tools(self, release_id: str, bindings: list[dict[str, Any]], reason: str) -> dict[str, Any]:
        async with self.db.transaction() as conn:
            cur = await conn.execute(
                "SELECT status FROM healthmind.workflow_releases WHERE release_id=%s FOR UPDATE", (release_id,)
            )
            release = await cur.fetchone()
            if not release:
                raise RuntimeError("release not found")
            if release["status"] != "candidate":
                raise RuntimeError("仅 candidate 版本允许修改工具绑定")
            codes = [b["tool_code"] for b in bindings]
            cur = await conn.execute(
                "SELECT tool_id, tool_code, auth_scope FROM healthmind.ai_tool_definitions"
                " WHERE active AND tool_code = ANY(%s)",
                (codes,),
            )
            definitions = await cur.fetchall()
            found = {d["tool_code"]: d for d in definitions}
            missing = [c for c in codes if c not in found]
            if missing:
                raise RuntimeError("active tool definitions missing: " + ", ".join(missing))
            await conn.execute("DELETE FROM healthmind.workflow_release_tools WHERE release_id=%s", (release_id,))
            for binding in bindings:
                definition = found[binding["tool_code"]]
                await conn.execute(
                    "INSERT INTO healthmind.workflow_release_tools(release_id, tool_id, allowed_scope, required, max_calls, timeout_ms)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (release_id, definition["tool_id"], definition["auth_scope"],
                     binding.get("required", True), binding.get("max_calls", 1), binding.get("timeout_ms", 10000)),
                )
            await conn.execute(
                "INSERT INTO healthmind.workflow_release_audits(audit_id, release_id, action, from_status, to_status, reason, change_metadata)"
                " VALUES (%s, %s, 'tools_bound', 'candidate', 'candidate', %s, %s)",
                (uuid4(), release_id, reason, Jsonb({"tool_codes": codes})),
            )
        return {"release_id": release_id, "bound": codes}

    async def transition_release(self, rid: str, operation: str, reason: str) -> None:
        async with self.db.transaction() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('healthmind.workflow.production',0))")
            cur = await conn.execute(
                "SELECT status, task_type_id FROM healthmind.workflow_releases WHERE release_id=%s FOR UPDATE", (rid,)
            )
            release = await cur.fetchone()
            if not release:
                raise RuntimeError("release not found")
            old = release["status"]
            if operation in {"promote", "rollback"}:
                cur = await conn.execute(
                    "SELECT release_id FROM healthmind.workflow_releases WHERE task_type_id=%s AND status='production'"
                    " AND release_id<>%s FOR UPDATE",
                    (release["task_type_id"], rid),
                )
                replaced = await cur.fetchone()
                await conn.execute(
                    "UPDATE healthmind.workflow_releases SET status='retired', retired_at=now()"
                    " WHERE task_type_id=%s AND status='production' AND release_id<>%s",
                    (release["task_type_id"], rid),
                )
                if replaced:
                    await conn.execute(
                        "INSERT INTO healthmind.workflow_release_audits(audit_id, release_id, action, from_status, to_status, reason)"
                        " VALUES (%s, %s, 'retired', 'production', 'retired', %s)",
                        (uuid4(), replaced["release_id"], f"Replaced by {rid}: {reason}"),
                    )
                await conn.execute(
                    "UPDATE healthmind.workflow_releases SET status='production', promoted_at=now(), retired_at=NULL"
                    " WHERE release_id=%s",
                    (rid,),
                )
                new = "production"
            elif operation == "retire":
                await conn.execute(
                    "UPDATE healthmind.workflow_releases SET status='retired', retired_at=now() WHERE release_id=%s", (rid,)
                )
                new = "retired"
            else:
                raise RuntimeError("unsupported transition")
            action = "rolled_back" if operation == "rollback" else ("promoted" if new == "production" else "retired")
            await conn.execute(
                "INSERT INTO healthmind.workflow_release_audits(audit_id, release_id, action, from_status, to_status, reason)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (uuid4(), rid, action, old, new, reason),
            )
