from typing import Any


class TraceMixin:
    """端到端链路搜索（关系优先，ILIKE 兜底并标注 matched=fuzzy）。"""

    # stage_key -> (显示标签, 行浏览器 kind)
    STAGES = [
        ("captures", "采集会话", "nutri_meal_capture_sessions"),
        ("nutri_outbox", "Nutri 出件箱 (capture-ready)", "nutri_integration_outbox"),
        ("healthmind_inbox", "HealthMind 收件箱", "healthmind_integration_inbox"),
        ("tasks", "AI 任务", "healthmind_ai_tasks"),
        ("attempts", "任务尝试", "healthmind_ai_task_attempts"),
        ("tool_invocations", "MCP 工具调用", "healthmind_ai_tool_invocations"),
        ("results", "任务结果", "healthmind_ai_task_results"),
        ("healthmind_outbox", "HealthMind 出件箱", "healthmind_integration_outbox"),
        ("nutri_inbox", "NutriMemo 收件箱", "nutri_integration_inbox"),
        ("meals", "餐食记录", "nutri_meal_records"),
    ]

    def _queries(self, value: str) -> dict[str, dict[str, Any]]:
        needle = f"%{value}%"
        return {
            "captures": {
                "exact": "SELECT * FROM nutri.meal_capture_sessions WHERE capture_session_id::text=%s ORDER BY created_at",
                "args": (value,),
            },
            "nutri_outbox": {
                "exact": "SELECT * FROM nutri.integration_outbox WHERE event_id::text=%s OR aggregate_id::text=%s ORDER BY created_at",
                "fuzzy": "SELECT * FROM nutri.integration_outbox WHERE payload::text ILIKE %s ORDER BY created_at",
                "args": (value, value), "fuzzy_args": (needle,),
            },
            "healthmind_inbox": {
                "exact": """SELECT i.* FROM healthmind.integration_inbox i
                     WHERE i.event_id::text=%s OR i.trace_id=%s OR i.aggregate_id=%s
                        OR i.payload_sha256=(SELECT o.payload_sha256 FROM healthmind.integration_outbox o
                                              WHERE o.event_id::text=%s OR o.task_id::text=%s OR o.trace_id=%s LIMIT 1)
                     ORDER BY i.received_at""",
                "args": (value, value, value, value, value, value),
            },
            "tasks": {
                "exact": """SELECT * FROM healthmind.ai_tasks
                     WHERE task_id::text=%s OR trace_id=%s OR aggregate_id=%s OR request_event_id::text=%s ORDER BY created_at""",
                "fuzzy": "SELECT * FROM healthmind.ai_tasks WHERE context_manifest::text ILIKE %s ORDER BY created_at",
                "args": (value, value, value, value), "fuzzy_args": (needle,),
            },
            "attempts": {
                "exact": """SELECT a.* FROM healthmind.ai_task_attempts a
                     JOIN healthmind.ai_tasks t USING (task_id)
                     WHERE a.attempt_id::text=%s OR t.task_id::text=%s OR t.trace_id=%s ORDER BY a.created_at""",
                "args": (value, value, value),
            },
            "tool_invocations": {
                "exact": """SELECT i.* FROM healthmind.ai_tool_invocations i
                     JOIN healthmind.ai_tasks t USING (task_id)
                     WHERE i.task_id::text=%s OR i.attempt_id::text=%s OR i.trace_id=%s ORDER BY i.created_at""",
                "args": (value, value, value),
            },
            "results": {
                "exact": """SELECT r.* FROM healthmind.ai_task_results r
                     JOIN healthmind.ai_tasks t USING (task_id)
                     WHERE r.task_id::text=%s OR r.result_id::text=%s OR t.trace_id=%s ORDER BY r.created_at""",
                "args": (value, value, value),
            },
            "healthmind_outbox": {
                "exact": """SELECT * FROM healthmind.integration_outbox
                     WHERE event_id::text=%s OR task_id::text=%s OR trace_id=%s OR aggregate_id=%s ORDER BY created_at""",
                "args": (value, value, value, value),
            },
            "nutri_inbox": {
                "exact": """SELECT i.* FROM nutri.integration_inbox i
                     LEFT JOIN healthmind.integration_outbox o ON o.payload_sha256=i.payload_sha256
                     WHERE i.event_id::text=%s OR o.event_id::text=%s OR o.task_id::text=%s OR o.trace_id=%s ORDER BY i.created_at""",
                "args": (value, value, value, value),
            },
            "meals": {
                "exact": """SELECT m.*, s.status AS capture_status
                     FROM nutri.meal_records m
                     JOIN nutri.meal_capture_sessions s USING (capture_session_id)
                     WHERE m.meal_id::text=%s OR m.capture_session_id::text=%s ORDER BY m.created_at""",
                "args": (value, value),
            },
        }

    async def trace(self, value: str) -> dict[str, Any]:
        stages: list[dict[str, Any]] = []
        for key, label, kind in self.STAGES:
            spec = self._queries(value)[key]
            rows: list[dict[str, Any]] = []
            matched: str | None = None
            rows = await self.db.fetch_all(spec["exact"], spec["args"])
            if not rows and spec.get("fuzzy"):
                rows = await self.db.fetch_all(spec["fuzzy"], spec.get("fuzzy_args", ()))
                if rows:
                    matched = "fuzzy"
            elif rows:
                matched = "exact"
            if rows:
                stages.append({
                    "stage": key, "label": label, "kind": kind,
                    "matched": matched, "rows": rows[:60],
                })
        return {"query": value, "stages": stages}
