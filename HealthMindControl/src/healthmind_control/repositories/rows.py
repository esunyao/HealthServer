from typing import Any, Literal

from ..util import decode_cursor, encode_cursor


class RowKind:
    """行浏览器注册项：标识表、主键、时间列、可用筛选列与列表投影（小列）。"""

    def __init__(self, key: str, table: str, label: str, id_col: str, id_type: Literal["uuid", "bigint"],
                 time_col: str, columns: list[str], filters: dict[str, str]):
        self.key = key
        self.table = table
        self.label = label
        self.id_col = id_col
        self.id_type = id_type
        self.time_col = time_col
        self.columns = columns
        self.filters = filters  # 筛选名 -> 实际列名


ROW_KINDS: dict[str, RowKind] = {k.key: k for k in [
    RowKind("healthmind_ai_tasks", "healthmind.ai_tasks", "AI 任务", "task_id", "uuid", "created_at",
            ["task_id", "trace_id", "status", "requester_service", "aggregate_type", "aggregate_id", "subject_id",
             "priority", "scheduled_at", "next_attempt_at", "created_at", "updated_at", "started_at", "completed_at",
             "deadline_at", "failure_code", "failure_message", "lock_version", "retention_until"],
            {"status": "status", "code": "failure_code", "service": "requester_service", "subject_id": "subject_id"}),
    RowKind("healthmind_ai_task_attempts", "healthmind.ai_task_attempts", "AI 任务尝试", "attempt_id", "uuid", "created_at",
            ["attempt_id", "task_id", "attempt_no", "status", "dify_workflow_run_id", "provider_name", "model_name",
             "started_at", "finished_at", "duration_ms", "timeout_ms", "input_tokens", "output_tokens",
             "estimated_cost", "failure_category", "failure_code", "failure_message", "created_at"],
            {"status": "status", "code": "failure_code"}),
    RowKind("healthmind_ai_task_results", "healthmind.ai_task_results", "AI 任务结果", "result_id", "uuid", "created_at",
            ["result_id", "task_id", "output_schema_version", "result_sha256", "confidence", "produced_at", "expires_at", "created_at"],
            {"status": "status"}),
    RowKind("healthmind_ai_tool_invocations", "healthmind.ai_tool_invocations", "MCP 工具调用", "invocation_id", "uuid", "created_at",
            ["invocation_id", "task_id", "attempt_id", "tool_call_id", "tool_id", "status", "authorized_scope",
             "started_at", "completed_at", "duration_ms", "failure_code", "failure_message", "trace_id", "created_at"],
            {"status": "status", "code": "failure_code"}),
    RowKind("healthmind_workflow_releases", "healthmind.workflow_releases", "Workflow 版本", "release_id", "uuid", "created_at",
            ["release_id", "task_type_id", "release_version", "status", "dify_workspace_id", "dify_app_id",
             "dify_workflow_id", "dify_workflow_version", "input_schema_version", "input_schema_sha256",
             "output_schema_version", "output_schema_sha256", "promoted_at", "retired_at", "created_at"],
            {"status": "status"}),
    RowKind("healthmind_integration_inbox", "healthmind.integration_inbox", "HealthMind 收件箱", "event_id", "uuid", "received_at",
            ["event_id", "event_type", "schema_version", "producer", "subject_id", "aggregate_type", "aggregate_id",
             "trace_id", "payload_sha256", "status", "attempt_count", "received_at", "processed_at",
             "failure_code", "failure_message"],
            {"status": "status", "code": "failure_code", "service": "producer", "subject_id": "subject_id"}),
    RowKind("healthmind_integration_outbox", "healthmind.integration_outbox", "HealthMind 出件箱", "event_id", "uuid", "created_at",
            ["event_id", "task_id", "event_type", "schema_version", "producer", "aggregate_type", "aggregate_id",
             "destination_key", "partition_key", "payload_sha256", "status", "attempt_count", "next_attempt_at",
             "published_at", "failure_code", "failure_message", "trace_id", "created_at"],
            {"status": "status", "code": "failure_code", "service": "producer"}),
    RowKind("nutri_meal_capture_sessions", "nutri.meal_capture_sessions", "采集会话", "capture_session_id", "uuid", "created_at",
            ["capture_session_id", "user_id", "client_request_id", "source", "status", "timezone", "max_image_count",
             "expires_at", "analysis_requested_at", "completed_at", "failed_at", "created_at", "updated_at"],
            {"status": "status", "subject_id": "user_id"}),
    RowKind("nutri_meal_capture_images", "nutri.meal_capture_images", "采集图片", "image_id", "bigint", "created_at",
            ["image_id", "capture_session_id", "slot_no", "bucket", "object_key", "content_type",
             "content_length", "captured_at", "status", "confirmed_at", "deleted_at", "created_at"],
            {"status": "status"}),
    RowKind("nutri_meal_records", "nutri.meal_records", "餐食记录", "meal_id", "bigint", "created_at",
            ["meal_id", "capture_session_id", "user_id", "meal_type", "consumed_at", "timezone", "local_date",
             "entry_source", "notes", "analysis_status", "status", "created_at", "updated_at", "deleted_at"],
            {"status": "status", "analysis": "analysis_status", "subject_id": "user_id"}),
    RowKind("nutri_meal_items", "nutri.meal_items", "餐食条目", "item_id", "bigint", "created_at",
            ["item_id", "meal_id", "sequence_no", "display_name", "estimated_weight_g", "confidence",
             "data_source", "user_corrected", "notes", "created_at", "updated_at"],
            {"status": "status"}),
    RowKind("nutri_integration_inbox", "nutri.integration_inbox", "NutriMemo 收件箱", "event_id", "uuid", "created_at",
            ["event_id", "event_type", "source_service", "payload_sha256", "status", "attempt_count",
             "processed_at", "last_error", "created_at", "updated_at"],
            {"status": "status", "code": "last_error", "service": "source_service"}),
    RowKind("nutri_integration_outbox", "nutri.integration_outbox", "NutriMemo 出件箱", "event_id", "uuid", "created_at",
            ["event_id", "aggregate_id", "aggregate_type", "event_type", "status", "attempt_count",
             "next_attempt_at", "published_at", "last_error", "locked_at", "created_at", "updated_at"],
            {"status": "status", "code": "last_error"}),
]}

FILTERABLE = ("status", "analysis", "code", "service", "subject_id")
TIME_FILTERS = ("since", "until")


def get_kind(kind: str) -> RowKind:
    item = ROW_KINDS.get(kind)
    if not item:
        raise KeyError(f"unknown row kind: {kind}")
    return item


class RowsMixin:
    """受控行浏览器：allowlist 注册表 + keyset 列表 + 详情。"""

    async def rows_meta(self) -> list[dict[str, Any]]:
        return [{
            "key": k.key, "label": k.label, "table": k.table, "id_col": k.id_col, "id_type": k.id_type,
            "time_col": k.time_col, "columns": k.columns,
            "filters": [name for name in ("status", "analysis", "code", "service", "subject_id") if name in k.filters],
        } for k in ROW_KINDS.values()]

    async def list_rows(self, kind: str, status: str | None = None, analysis: str | None = None,
                        code: str | None = None, service: str | None = None, subject_id: str | None = None,
                        since: str | None = None, until: str | None = None,
                        cursor: str | None = None, limit: int = 50) -> dict[str, Any]:
        meta = get_kind(kind)
        clauses: list[str] = []
        params: list[Any] = []
        for name, value in (("status", status), ("analysis", analysis), ("code", code),
                            ("service", service), ("subject_id", subject_id)):
            if not value:
                continue
            column = meta.filters.get(name)
            if not column:
                continue
            clauses.append(f"{column} = %s")
            params.append(value)
        if since:
            clauses.append(f"{meta.time_col} >= %s::timestamptz"); params.append(since)
        if until:
            clauses.append(f"{meta.time_col} <= %s::timestamptz"); params.append(until)
        decoded = decode_cursor(cursor) if cursor else None
        if decoded:
            clauses.append(f"({meta.time_col}, {meta.id_col}) < (%s::timestamptz, %s::{meta.id_type})")
            params.extend(decoded)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        columns = ", ".join(meta.columns)
        params.append(limit + 1)
        rows = await self.db.fetch_all(f"""
            SELECT {columns} FROM {meta.table} {where}
            ORDER BY {meta.time_col} DESC, {meta.id_col} DESC LIMIT %s
        """, tuple(params))
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(last[meta.time_col].isoformat(), str(last[meta.id_col]))
        return {"kind": kind, "items": items, "next_cursor": next_cursor, "has_more": has_more}

    async def row_detail(self, kind: str, row_id: str) -> dict[str, Any] | None:
        meta = get_kind(kind)
        if meta.id_type == "bigint":
            try:
                row_id = str(int(row_id))
            except ValueError:
                return None
        return await self.db.fetch_one(f"SELECT * FROM {meta.table} WHERE {meta.id_col} = %s", (row_id,))
