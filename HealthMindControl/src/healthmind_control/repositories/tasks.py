from typing import Any
from uuid import UUID

from ..util import decode_cursor, encode_cursor


def _uuid_or_none(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


class TasksMixin:
    """AI 任务：筛选/keyset 分页列表（轻量投影）与任务详情聚合。"""

    async def list_tasks(self, status: str | None = None, task_type: str | None = None,
                         service: str | None = None, code: str | None = None,
                         subject: str | None = None, since: str | None = None,
                         until: str | None = None, cursor: str | None = None,
                         limit: int = 50) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("t.status = %s"); params.append(status)
        if task_type:
            clauses.append("tt.task_type_code = %s"); params.append(task_type)
        if service:
            clauses.append("t.requester_service = %s"); params.append(service)
        if code:
            clauses.append("t.failure_code = %s"); params.append(code)
        subject_uuid = _uuid_or_none(subject)
        if subject_uuid:
            clauses.append("t.subject_id = %s"); params.append(subject_uuid)
        if since:
            clauses.append("t.created_at >= %s::timestamptz"); params.append(since)
        if until:
            clauses.append("t.created_at <= %s::timestamptz"); params.append(until)
        decoded = decode_cursor(cursor) if cursor else None
        if decoded:
            clauses.append("(t.created_at, t.task_id) < (%s::timestamptz, %s::uuid)")
            params.extend(decoded)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit + 1)
        rows = await self.db.fetch_all(f"""
            SELECT t.task_id, t.trace_id, t.status, t.request_event_id, tt.task_type_code,
                   wr.release_version, t.requester_service, t.aggregate_type, t.aggregate_id,
                   t.subject_id, t.priority, t.scheduled_at, t.next_attempt_at, t.created_at,
                   t.updated_at, t.started_at, t.completed_at, t.deadline_at,
                   t.failure_code, t.failure_message, t.lock_version,
                   (SELECT count(*)::int FROM healthmind.ai_task_attempts a WHERE a.task_id = t.task_id) AS attempt_count
              FROM healthmind.ai_tasks t
              JOIN healthmind.ai_task_types tt USING (task_type_id)
              JOIN healthmind.workflow_releases wr ON wr.release_id = t.workflow_release_id
              {where}
             ORDER BY t.created_at DESC, t.task_id DESC LIMIT %s
        """, tuple(params))
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(last["created_at"].isoformat(), str(last["task_id"]))
        return {"items": items, "next_cursor": next_cursor, "has_more": has_more}

    async def task_bundle(self, task_id: str) -> dict[str, Any]:
        """任务详情聚合：全字段任务 + 尝试 + 工具调用 + 结果 + outbox + 关联餐食。"""
        task = await self.db.fetch_one("SELECT * FROM healthmind.ai_tasks WHERE task_id = %s", (task_id,))
        if not task:
            return {"task": None}
        attempts = await self.db.fetch_all(
            "SELECT * FROM healthmind.ai_task_attempts WHERE task_id = %s ORDER BY attempt_no", (task_id,)
        )
        invocations = await self.db.fetch_all(
            "SELECT * FROM healthmind.ai_tool_invocations WHERE task_id = %s ORDER BY created_at", (task_id,)
        )
        results = await self.db.fetch_all(
            "SELECT * FROM healthmind.ai_task_results WHERE task_id = %s", (task_id,)
        )
        outbox = await self.db.fetch_all("""
            SELECT event_id, event_type, status, destination_key, partition_key, payload_sha256,
                   attempt_count, published_at, failure_code, failure_message, trace_id, created_at
              FROM healthmind.integration_outbox WHERE task_id = %s ORDER BY created_at
        """, (task_id,))
        meal = None
        manifest = task.get("context_manifest") or {}
        meal_id, capture_id = manifest.get("meal_id"), manifest.get("capture_session_id")
        if meal_id is not None and capture_id:
            meal = await self.db.fetch_one("""
                SELECT m.meal_id, m.capture_session_id, m.meal_type, m.consumed_at, m.timezone,
                       m.local_date, m.analysis_status, m.status, m.created_at, m.updated_at,
                       s.status AS capture_status, s.analysis_requested_at, s.completed_at, s.failed_at,
                       (SELECT count(*)::int FROM nutri.meal_capture_images i
                         WHERE i.capture_session_id = m.capture_session_id AND i.status = 'confirmed') AS confirmed_images
                  FROM nutri.meal_records m
                  JOIN nutri.meal_capture_sessions s USING (capture_session_id)
                 WHERE m.meal_id = %s AND m.capture_session_id = %s
            """, (int(meal_id), str(capture_id)))
        return {"task": task, "attempts": attempts, "invocations": invocations,
                "results": results, "outbox": outbox, "meal": meal}
