from typing import Any


class OverviewMixin:
    """总览与滞留数据：轻量摘要、生产版本卡、滞留/不一致清单（含新增检测项）。"""

    # ---------------------------------------------------------------- 摘要
    async def status_light(self) -> dict[str, Any]:
        if not self.db.pool:
            return {"database": {"ok": False, "error": self.db.schema_error}}
        tasks = await self.db.fetch_all(
            "SELECT status, count(*)::int AS count FROM healthmind.ai_tasks GROUP BY status ORDER BY status"
        )
        production = await self.db.fetch_one("""
            SELECT wr.release_id, wr.release_version, wr.status, wr.dify_workspace_id, wr.dify_app_id,
                   wr.dify_workflow_id, wr.dify_workflow_version, wr.dify_workflow_version AS workflow_version,
                   wr.input_schema_version, wr.input_schema_sha256, wr.output_schema_version, wr.output_schema_sha256,
                   wr.promoted_at, tt.task_type_code,
                   COALESCE(jsonb_agg(jsonb_build_object('tool_code', td.tool_code, 'scope', rt.allowed_scope))
                     FILTER (WHERE td.tool_id IS NOT NULL), '[]'::jsonb) AS tools
              FROM healthmind.workflow_releases wr
              JOIN healthmind.ai_task_types tt USING (task_type_id)
              LEFT JOIN healthmind.workflow_release_tools rt USING (release_id)
              LEFT JOIN healthmind.ai_tool_definitions td USING (tool_id)
             WHERE wr.status = 'production' AND tt.task_type_code = 'nutrition.meal_analysis'
             GROUP BY wr.release_id, tt.task_type_code
        """)
        failures = await self.db.fetch_all("""
            SELECT task_id, status, failure_code, failure_message, created_at, started_at, completed_at
              FROM healthmind.ai_tasks
             WHERE status = 'failed'
             ORDER BY completed_at DESC NULLS LAST LIMIT 8
        """)
        for row in failures:
            started, finished = row.get("started_at"), row.get("completed_at")
            row["duration_ms"] = self._duration_ms(started, finished)
            row.pop("started_at", None)
            row.pop("created_at", None)
        return {
            "database": {
                "ok": True,
                "write_enabled": self.db.write_enabled,
                "schema_error": self.db.schema_error,
            },
            "tasks": tasks,
            "production": production,
            "recent_failures": failures,
        }

    @staticmethod
    def _duration_ms(started: Any, finished: Any) -> int | None:
        if started is None or finished is None:
            return None
        delta = finished - started
        return int(delta.total_seconds() * 1000) if delta is not None else None

    # ---------------------------------------------------------------- 滞留与不一致
    async def backlogs(self) -> dict[str, Any]:
        stale_after = self.stale_minutes
        stale = await self.db.fetch_all("""
          SELECT 'task.queued_or_running' AS source, task_id::text AS id, status,
                 updated_at AS at, 'task' AS kind, 'healthmind' AS schema_name
            FROM healthmind.ai_tasks
           WHERE status IN ('queued', 'running') AND updated_at < now() - (%s * interval '1 minute')
          UNION ALL
          SELECT 'healthmind.outbox', event_id::text, status, created_at, 'outbox', 'healthmind'
            FROM healthmind.integration_outbox
           WHERE status IN ('pending', 'publishing', 'failed') AND created_at < now() - (%s * interval '1 minute')
          UNION ALL
          SELECT 'nutri.outbox', event_id::text, status, created_at, 'outbox', 'nutri'
            FROM nutri.integration_outbox
           WHERE status IN ('pending', 'publishing', 'failed') AND created_at < now() - (%s * interval '1 minute')
          ORDER BY at LIMIT 100
        """, (stale_after, stale_after, stale_after))

        attempts_stale = await self.db.fetch_all("""
            SELECT a.attempt_id::text AS id, a.task_id::text AS task_id, a.attempt_no, t.status AS task_status,
                   a.started_at + (a.timeout_ms * interval '1 millisecond') AS deadline, now() AS at
              FROM healthmind.ai_task_attempts a
              JOIN healthmind.ai_tasks t USING (task_id)
             WHERE a.status = 'running' AND t.status = 'running'
               AND a.started_at + (a.timeout_ms * interval '1 millisecond') < now()
             ORDER BY deadline LIMIT 100
        """)

        inbox_stale = await self.db.fetch_all("""
            SELECT 'healthmind.inbox' AS source, event_id::text AS id, status, received_at AS at
              FROM healthmind.integration_inbox
             WHERE status = 'processing' AND received_at < now() - (%s * interval '1 minute')
            UNION ALL
            SELECT 'nutri.inbox', event_id::text, status, created_at
              FROM nutri.integration_inbox
             WHERE status = 'processing' AND created_at < now() - (%s * interval '1 minute')
            ORDER BY at LIMIT 100
        """, (stale_after, stale_after))

        # 已发布但下游迟迟未出现对应 inbox / 未生成任务的事件
        unconsumed = await self.db.fetch_all("""
            (SELECT 'hm-outbox-unconsumed' AS source, event_id::text AS id, event_type, published_at AS at,
                    destination_key, 'healthmind' AS schema_name
               FROM healthmind.integration_outbox o
              WHERE o.status = 'published'
                AND o.published_at < now() - (%s * interval '1 minute')
                AND NOT EXISTS (SELECT 1 FROM nutri.integration_inbox i WHERE i.payload_sha256 = o.payload_sha256))
            UNION ALL
            (SELECT 'nutri-capture-ready-stalled' AS source, o.event_id::text, o.event_type, o.published_at,
                    'nutrition-capture-ready', 'nutri'
               FROM nutri.integration_outbox o
              WHERE o.status = 'published'
                AND o.published_at < now() - (%s * interval '1 minute')
                AND NOT EXISTS (SELECT 1 FROM healthmind.integration_inbox i WHERE i.event_id = o.event_id)
                AND NOT EXISTS (SELECT 1 FROM healthmind.ai_tasks t WHERE t.request_event_id = o.event_id))
            ORDER BY at LIMIT 100
        """, (stale_after, stale_after))

        inconsistent = await self.db.fetch_all("""
            SELECT m.meal_id, m.capture_session_id, m.analysis_status, s.status AS capture_status,
                   t.status AS task_status, t.task_id
              FROM nutri.meal_records m
              JOIN nutri.meal_capture_sessions s USING (capture_session_id)
              LEFT JOIN LATERAL (
                SELECT task_id, status FROM healthmind.ai_tasks
                 WHERE aggregate_id = m.meal_id::text ORDER BY created_at DESC LIMIT 1
              ) t ON true
             WHERE (m.analysis_status = 'completed' AND s.status <> 'completed')
                OR (m.analysis_status = 'analysing'
                    AND (t.status IS NULL OR t.status IN ('failed', 'cancelled', 'expired')))
             ORDER BY m.updated_at DESC LIMIT 100
        """)
        counts = await self.db.fetch_all("""
            SELECT 'healthmind.inbox' source, status, count(*)::int count FROM healthmind.integration_inbox GROUP BY status
            UNION ALL SELECT 'healthmind.outbox', status, count(*)::int FROM healthmind.integration_outbox GROUP BY status
            UNION ALL SELECT 'nutri.inbox', status, count(*)::int FROM nutri.integration_inbox GROUP BY status
            UNION ALL SELECT 'nutri.outbox', status, count(*)::int FROM nutri.integration_outbox GROUP BY status
            ORDER BY 1, 2
        """)
        return {
            "counts": counts,
            "stale": stale,
            "attempts_stale": attempts_stale,
            "inbox_stale": inbox_stale,
            "unconsumed": unconsumed,
            "inconsistent": inconsistent,
        }
