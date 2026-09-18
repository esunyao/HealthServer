from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ..security import sha256_json

FAILURE_TOPIC = "nutrition-analysis-failed"
FAILURE_EVENT_TYPE = "nutrition.analysis.failed.v1"
CAPTURE_TOPIC = "nutrition-capture-ready"
CAPTURE_EVENT_TYPE = "nutrition.capture.ready.v1"


class RecoveryMixin:
    """受控修复：重置/重放/取消/attempt 恢复（重排或发 failure 事件）/克隆任务。"""

    # ------------------------------------------------------------ 消息源解析
    async def replay_message(self, schema: str, record_id: str, from_inbox: bool = False) -> dict[str, Any]:
        """published outbox 原样重放 / failed inbox 经同 event 的 HM outbox 重放。"""
        if from_inbox:
            row = await self.db.fetch_one("""SELECT o.destination_key AS topic, o.partition_key AS key, o.payload
                FROM nutri.integration_inbox i
                JOIN healthmind.integration_outbox o ON o.event_id = i.event_id
               WHERE i.event_id = %s AND i.status = 'failed'""", (record_id,))
        elif schema == "healthmind":
            row = await self.db.fetch_one(
                "SELECT destination_key AS topic, partition_key AS key, payload FROM healthmind.integration_outbox"
                " WHERE event_id=%s AND status='published'", (record_id,)
            )
        else:
            row = await self.db.fetch_one(
                "SELECT %s AS topic, aggregate_id::text AS key, payload FROM nutri.integration_outbox"
                " WHERE event_id=%s AND status='published'",
                (CAPTURE_TOPIC, record_id),
            )
        if not row:
            raise RuntimeError("可重放的已发布 outbox/失败 inbox 不存在")
        return row

    async def hm_capture_ready_message(self, record_id: str) -> dict[str, Any]:
        """HealthMind 收件箱缺失场景：取 capture-ready 源事件并做存在性预检。"""
        row = await self.db.fetch_one("""
            SELECT event_id, aggregate_id, payload FROM nutri.integration_outbox
             WHERE event_id = %s AND status = 'published' AND event_type = %s
        """, (record_id, CAPTURE_EVENT_TYPE))
        if not row:
            raise RuntimeError("未找到已发布的 capture-ready 事件（nutri 出件箱）")
        inbox = await self.db.fetch_one(
            "SELECT status FROM healthmind.integration_inbox WHERE event_id = %s", (record_id,)
        )
        if inbox:
            raise RuntimeError(f"HealthMind 收件箱已存在（status={inbox['status']}）：请改用克隆任务重试，不要重置收件箱")
        task = await self.db.fetch_one(
            "SELECT task_id FROM healthmind.ai_tasks WHERE request_event_id = %s", (record_id,)
        )
        if task:
            raise RuntimeError(f"该事件已生成任务 {task['task_id']}：请改用克隆任务重试")
        return {"topic": CAPTURE_TOPIC, "key": str(row["aggregate_id"]), "payload": row["payload"]}

    # ------------------------------------------------------------ 克隆失败任务
    async def retry_validation(self, task_id: str) -> dict[str, Any]:
        task = await self.db.fetch_one("SELECT * FROM healthmind.ai_tasks WHERE task_id = %s", (task_id,))
        if not task:
            raise RuntimeError("task not found")
        manifest = task.get("context_manifest") or {}
        meal_id, capture_id = manifest.get("meal_id"), manifest.get("capture_session_id")
        meal_info: dict[str, Any] | None = None
        reasons: list[str] = []
        try:
            meal_ref = int(meal_id), str(UUID(str(capture_id)))
        except (TypeError, ValueError):
            meal_ref = None
        if meal_ref is None:
            reasons.append("任务 context_manifest 的 meal_id/capture_session_id 缺失或格式无效")
        else:
            meal_info = await self.db.fetch_one("""
                SELECT m.meal_id, m.status AS meal_status, m.analysis_status,
                       s.status AS capture_status,
                       (SELECT count(*)::int FROM nutri.meal_capture_images i
                         WHERE i.capture_session_id = m.capture_session_id AND i.status = 'confirmed') AS confirmed_images
                  FROM nutri.meal_records m
                  JOIN nutri.meal_capture_sessions s USING (capture_session_id)
                 WHERE m.meal_id = %s AND m.capture_session_id = %s
            """, meal_ref)
            if not meal_info:
                reasons.append("关联餐食记录不存在")
            else:
                if meal_info["meal_status"] != "active":
                    reasons.append(f"餐食状态不是 active（当前 {meal_info['meal_status']}）")
                if (meal_info["confirmed_images"] or 0) < 1:
                    reasons.append("没有已确认的采集图片")
        releases = await self.db.fetch_all("""
            SELECT release_id, release_version, status FROM healthmind.workflow_releases
             WHERE task_type_id = %s ORDER BY created_at DESC LIMIT 20
        """, (task["task_type_id"],))
        return {
            "task": {"task_id": task_id, "status": task["status"], "trace_id": task["trace_id"]},
            "meal": meal_info, "reasons": reasons,
            "releases": releases,
            "clonable": task["status"] in ("failed", "cancelled", "expired") and not reasons,
        }

    async def retry_task(self, task_id: str, release_id: str | None, reason: str, operation_id: str) -> str:
        new_id = str(uuid4())
        async with self.db.transaction() as conn:
            cur = await conn.execute("SELECT * FROM healthmind.ai_tasks WHERE task_id=%s FOR UPDATE", (task_id,))
            old = await cur.fetchone()
            if not old or old["status"] not in ("failed", "cancelled", "expired"):
                raise RuntimeError("only terminal failed/cancelled/expired tasks can be cloned")
            selected = release_id
            if not selected:
                cur = await conn.execute(
                    "SELECT release_id FROM healthmind.workflow_releases WHERE task_type_id=%s AND status='production'",
                    (old["task_type_id"],),
                )
                row = await cur.fetchone()
                selected = str(row["release_id"]) if row else None
            if not selected:
                raise RuntimeError("production release not found")
            cur = await conn.execute(
                "SELECT release_id FROM healthmind.workflow_releases WHERE release_id=%s AND task_type_id=%s",
                (selected, old["task_type_id"]),
            )
            if not await cur.fetchone():
                raise RuntimeError("selected release does not belong to the task type")
            manifest = dict(old["context_manifest"])
            manifest.update(admin_retry_of_task_id=task_id, admin_operation_id=operation_id, admin_reason=reason)
            capture_id, meal_id = manifest.get("capture_session_id"), manifest.get("meal_id")
            cur = await conn.execute("""SELECT m.status, m.analysis_status,
                (SELECT count(*) FROM nutri.meal_capture_images i
                  WHERE i.capture_session_id = m.capture_session_id AND i.status = 'confirmed') AS confirmed
                FROM nutri.meal_records m WHERE m.meal_id=%s AND m.capture_session_id=%s FOR UPDATE""",
                (meal_id, capture_id))
            meal = await cur.fetchone()
            if not meal or meal["status"] != "active" or meal["confirmed"] < 1:
                raise RuntimeError("active meal with confirmed images not found")
            cur = await conn.execute("""SELECT task_id,status FROM healthmind.ai_tasks
                WHERE aggregate_type=%s AND aggregate_id=%s
                  AND status IN ('queued','running') FOR UPDATE""",
                (old["aggregate_type"], old["aggregate_id"]))
            active = await cur.fetchone()
            if active:
                raise RuntimeError(f"active task already exists: {active['task_id']} ({active['status']})")
            await conn.execute("""INSERT INTO healthmind.ai_tasks
              (task_id, task_type_id, workflow_release_id, requester_service, subject_id, aggregate_type, aggregate_id,
               idempotency_key, invocation_mode, status, priority, trace_id, input_schema_version, input_digest,
               context_manifest, retention_until)
              SELECT %s, task_type_id, %s, 'HealthMindControl', subject_id, aggregate_type, aggregate_id, %s,
                     invocation_mode, 'queued', priority, trace_id,
                     (SELECT input_schema_version FROM healthmind.workflow_releases WHERE release_id=%s),
                     input_digest, %s, now() + (%s * interval '1 day')
                FROM healthmind.ai_tasks WHERE task_id=%s""",
              (new_id, selected, f"admin-retry:{task_id}:{selected}", selected, Jsonb(manifest),
               self.retention_days, task_id))
            await conn.execute(
                "UPDATE nutri.meal_records SET analysis_status='analysing'"
                " WHERE meal_id=%s AND analysis_status='failed'",
                (meal_id,),
            )
            await conn.execute(
                "UPDATE nutri.meal_capture_sessions SET status='analysing', failed_at=NULL"
                " WHERE capture_session_id=%s AND status='failed'",
                (capture_id,),
            )
        return new_id

    # ------------------------------------------------------------ 恢复类操作
    async def recover(self, operation: str, schema: str, record_id: str,
                      expected_lock_version: int | None = None) -> dict[str, Any]:
        if operation == "reset_outbox":
            return await self._reset_outbox(schema, record_id)
        if operation == "cancel_task":
            return await self._cancel_task(record_id)
        if operation == "recover_attempt":
            return await self._recover_attempt(record_id, expected_lock_version)
        raise RuntimeError("unsupported recovery")

    async def _reset_outbox(self, schema: str, record_id: str) -> dict[str, Any]:
        async with self.db.transaction() as conn:
            if schema == "healthmind":
                cur = await conn.execute("""UPDATE healthmind.integration_outbox
                    SET status='pending', next_attempt_at=now(), published_at=NULL,
                        failure_code=NULL, failure_message=NULL
                    WHERE event_id=%s AND (status='failed' OR
                      (status='publishing' AND next_attempt_at < now() - (%s * interval '1 minute')))
                    RETURNING event_id, status""", (record_id, self.stale_minutes))
            else:
                cur = await conn.execute("""UPDATE nutri.integration_outbox
                    SET status='pending', next_attempt_at=now(), published_at=NULL,
                        last_error=NULL, locked_at=NULL
                    WHERE event_id=%s AND (status='failed' OR
                      (status='publishing' AND locked_at < now() - (%s * interval '1 minute')))
                    RETURNING event_id, status""", (record_id, self.stale_minutes))
            row = await cur.fetchone()
            if not row:
                raise RuntimeError("record changed or operation precondition failed")
            return dict(row)

    async def _cancel_task(self, record_id: str) -> dict[str, Any]:
        async with self.db.transaction() as conn:
            cur = await conn.execute("""UPDATE healthmind.ai_tasks
                SET status='cancelled', completed_at=now(), lock_version=lock_version+1
                WHERE task_id=%s AND status='queued'
                RETURNING task_id,status,lock_version,trace_id,subject_id,aggregate_type,aggregate_id,context_manifest""", (record_id,))
            row = await cur.fetchone()
            if not row:
                raise RuntimeError("record changed or operation precondition failed（仅 queued 任务可取消）")
            event_id = str(uuid4())
            manifest = row.get("context_manifest") or {}
            envelope = self._failure_envelope(row, event_id, manifest, "TASK_CANCELLED", "cancelled",
                                              "Cancelled by HealthMindControl")
            await conn.execute("""INSERT INTO healthmind.integration_outbox
                (event_id,task_id,event_type,schema_version,producer,aggregate_type,aggregate_id,
                 destination_key,partition_key,payload,payload_sha256,trace_id,retention_until)
                VALUES (%s,%s,%s,'1.0','HealthMind',%s,%s,%s,%s,%s,%s,%s,
                        now() + (%s * interval '1 day'))""",
                (event_id, row["task_id"], FAILURE_EVENT_TYPE, row["aggregate_type"], row["aggregate_id"],
                 FAILURE_TOPIC, manifest.get("capture_session_id") or str(row["task_id"]), Jsonb(envelope),
                 sha256_json(envelope), row["trace_id"], self.retention_days))
            return {"task_id": row["task_id"], "status": row["status"], "lock_version": row["lock_version"],
                    "event_id": event_id}

    async def _recover_attempt(self, attempt_id: str, expected_lock_version: int | None) -> dict[str, Any]:
        """超时 running attempt：行锁 + lock_version 双校验后，有余次则重排任务，
        次数耗尽则将任务置 failed 并按标准结构写入 nutrition.analysis.failed.v1 outbox。"""
        if expected_lock_version is None:
            raise RuntimeError("expected_lock_version is required; preview again")
        async with self.db.transaction() as conn:
            cur = await conn.execute(
                "SELECT attempt_id, task_id, attempt_no, status, started_at, timeout_ms"
                " FROM healthmind.ai_task_attempts WHERE attempt_id=%s FOR UPDATE", (attempt_id,),
            )
            attempt = await cur.fetchone()
            if not attempt:
                raise RuntimeError("attempt not found")
            if attempt["status"] != "running":
                raise RuntimeError("attempt 已不是 running 状态，请重新预览")
            if attempt["started_at"] is None:
                raise RuntimeError("attempt 缺少 started_at，无法判定超时")
            cur = await conn.execute(
                "SELECT attempt_id FROM healthmind.ai_task_attempts WHERE task_id=%s ORDER BY attempt_no DESC LIMIT 1",
                (attempt["task_id"],),
            )
            latest = await cur.fetchone()
            if not latest or latest["attempt_id"] != attempt["attempt_id"]:
                raise RuntimeError("only the latest attempt may be recovered")
            deadline = attempt["started_at"] + timedelta(milliseconds=attempt["timeout_ms"])
            if deadline > datetime.now(UTC):
                raise RuntimeError("attempt 尚未超过 timeout 期限，无法人工恢复")

            cur = await conn.execute(
                "SELECT task_id, status, lock_version, trace_id, subject_id, aggregate_type, aggregate_id,"
                " workflow_release_id, context_manifest"
                " FROM healthmind.ai_tasks WHERE task_id=%s FOR UPDATE", (attempt["task_id"],),
            )
            task = await cur.fetchone()
            if not task:
                raise RuntimeError("task not found")
            if task["status"] != "running":
                raise RuntimeError(f"任务已不是 running（当前 {task['status']}），请重新预览")
            if task["lock_version"] != expected_lock_version:
                raise RuntimeError("任务 lock_version 在预览后变化，请重新预览")

            updated = await conn.execute("""UPDATE healthmind.ai_task_attempts
                SET status='timed_out', finished_at=now(), failure_category='timeout',
                    failure_code='ATTEMPT_TIMEOUT', failure_message='Recovered by HealthMindControl'
                WHERE attempt_id=%s AND status='running'""", (attempt_id,))
            if updated.rowcount != 1:
                raise RuntimeError("attempt 状态已被并发修改，请重新预览")

            cur = await conn.execute(
                "SELECT max_attempts FROM healthmind.workflow_releases WHERE release_id=%s", (task["workflow_release_id"],)
            )
            release = await cur.fetchone()
            max_attempts = (release or {}).get("max_attempts") or 3
            manifest = task.get("context_manifest") or {}
            if attempt["attempt_no"] < max_attempts:
                # 有剩余次数：原任务立即重新排队（保留 attempts 历史）
                await conn.execute("""UPDATE healthmind.ai_tasks
                    SET status='queued', next_attempt_at=now(), failure_code=NULL, failure_message=NULL,
                        lock_version=lock_version+1
                    WHERE task_id=%s AND status='running' AND lock_version=%s""",
                    (task["task_id"], task["lock_version"]))
                return {
                    "action": "requeued", "attempt_id": attempt_id, "task_id": task["task_id"],
                    "attempt_no": attempt["attempt_no"], "max_attempts": max_attempts,
                }

            # 次数耗尽：任务失败并写入标准 failure outbox 事件
            await conn.execute("""UPDATE healthmind.ai_tasks
                SET status='failed', completed_at=now(), failure_code='ATTEMPT_TIMEOUT',
                    failure_message='Recovered by HealthMindControl (attempts exhausted)',
                    lock_version=lock_version+1
                WHERE task_id=%s AND status='running' AND lock_version=%s""",
                (task["task_id"], task["lock_version"]))
            event_id = str(uuid4())
            occurred_at = datetime.now(UTC).isoformat()
            error_summary = "Recovered by HealthMindControl (attempts exhausted)"
            envelope = {
                "event_id": event_id,
                "event_type": FAILURE_EVENT_TYPE,
                "occurred_at": occurred_at,
                "producer": "HealthMind",
                "trace_id": task["trace_id"],
                "subject_id": str(task["subject_id"]) if task["subject_id"] else None,
                "aggregate_type": task["aggregate_type"],
                "aggregate_id": task["aggregate_id"],
                "schema_version": "1.0",
                "payload": {
                    "task_id": str(task["task_id"]),
                    "capture_session_id": manifest.get("capture_session_id"),
                    "meal_id": manifest.get("meal_id"),
                    "error_code": "ATTEMPT_TIMEOUT",
                    "failure_category": "timeout",
                    "retryable": False,
                    "error_summary": error_summary,
                },
            }
            await conn.execute("""INSERT INTO healthmind.integration_outbox
                (event_id, task_id, event_type, schema_version, producer, aggregate_type, aggregate_id,
                 destination_key, partition_key, payload, payload_sha256, trace_id, retention_until)
                VALUES (%s, %s, %s, '1.0', 'HealthMind', %s, %s, %s, %s, %s, %s, %s,
                        now() + (%s * interval '1 day'))""",
                (event_id, task["task_id"], FAILURE_EVENT_TYPE, task["aggregate_type"], task["aggregate_id"],
                 FAILURE_TOPIC, manifest.get("capture_session_id") or str(task["task_id"]),
                 Jsonb(envelope), sha256_json(envelope), task["trace_id"], self.retention_days))
            return {"action": "task_failed", "event_id": event_id, "task_id": task["task_id"],
                    "attempt_no": attempt["attempt_no"], "max_attempts": max_attempts}

    @staticmethod
    def _failure_envelope(task: dict[str, Any], event_id: str, manifest: dict[str, Any],
                          code: str, category: str, summary: str) -> dict[str, Any]:
        return {
            "event_id": event_id, "event_type": FAILURE_EVENT_TYPE,
            "occurred_at": datetime.now(UTC).isoformat(), "producer": "HealthMind",
            "trace_id": task["trace_id"],
            "subject_id": str(task["subject_id"]) if task.get("subject_id") else None,
            "aggregate_type": task["aggregate_type"], "aggregate_id": task["aggregate_id"],
            "schema_version": "1.0",
            "payload": {"task_id": str(task["task_id"]),
                        "capture_session_id": manifest.get("capture_session_id"),
                        "meal_id": manifest.get("meal_id"), "error_code": code,
                        "failure_category": category, "retryable": False, "error_summary": summary},
        }

    # ------------------------------------------------------------ 修复向导
    async def repair_guide(self, query: str) -> dict[str, Any]:
        """按 meal / event / task / capture 定位一条链路并给出可执行修复建议。"""
        found: dict[str, Any] = {}
        suggestions: list[dict[str, str]] = []
        tasks = await self.db.fetch_all("""
            SELECT task_id, status, trace_id, aggregate_id, context_manifest->>'meal_id' AS meal_id,
                   context_manifest->>'capture_session_id' AS capture_session_id, failure_code, created_at
              FROM healthmind.ai_tasks
             WHERE task_id::text=%s OR trace_id=%s OR aggregate_id=%s OR request_event_id::text=%s
             ORDER BY created_at DESC LIMIT 5
        """, (query, query, query, query))
        if tasks:
            found["tasks"] = tasks
            latest = tasks[0]
            if latest["status"] in ("failed", "cancelled", "expired"):
                validation = await self.retry_validation(str(latest["task_id"]))
                if validation["clonable"]:
                    suggestions.append({
                        "operation": "clone_task", "schema_name": "healthmind",
                        "record_id": str(latest["task_id"]),
                        "label": "克隆失败任务重试",
                        "note": f"{latest['status']} · trace {latest['trace_id'][:12]}… · meal {latest['meal_id']}",
                    })
                else:
                    suggestions.append({
                        "operation": "clone_task_blocked", "schema_name": "healthmind",
                        "record_id": str(latest["task_id"]), "label": "克隆失败任务（前置校验未通过）",
                        "note": "; ".join(validation["reasons"]) or "餐食/图片校验失败",
                    })
            elif latest["status"] == "queued":
                suggestions.append({
                    "operation": "cancel_task", "schema_name": "healthmind",
                    "record_id": str(latest["task_id"]), "label": "取消 queued 任务", "note": "仅 queued 可取消",
                })
        captures = await self.db.fetch_all("""
            SELECT capture_session_id, status, created_at FROM nutri.meal_capture_sessions
             WHERE capture_session_id::text=%s ORDER BY created_at DESC LIMIT 5
        """, (query,))
        if captures:
            found["captures"] = captures
        events = await self.db.fetch_all("""
            SELECT event_id, event_type, status, published_at, aggregate_id FROM nutri.integration_outbox
             WHERE event_id::text=%s OR aggregate_id::text=%s ORDER BY created_at DESC LIMIT 5
        """, (query, query))
        if events:
            found["nutri_outbox"] = events
            for event in events:
                if event["event_type"] == CAPTURE_EVENT_TYPE and event["status"] == "published":
                    inbox = await self.db.fetch_one(
                        "SELECT status FROM healthmind.integration_inbox WHERE event_id=%s", (event["event_id"],)
                    )
                    related_task = await self.db.fetch_one(
                        "SELECT task_id, status FROM healthmind.ai_tasks WHERE request_event_id=%s", (event["event_id"],)
                    )
                    if not inbox and not related_task:
                        suggestions.append({
                            "operation": "replay_hm_inbox", "schema_name": "nutri",
                            "record_id": str(event["event_id"]),
                            "label": "重放 capture-ready 补齐缺失的 HealthMind 收件箱",
                            "note": "同 event 无 inbox 且无任务，可安全重放",
                        })
                    elif inbox and inbox["status"] == "failed" and related_task:
                        suggestions.append({
                            "operation": "clone_task", "schema_name": "healthmind",
                            "record_id": str(related_task["task_id"]),
                            "label": "收件箱已存在 → 克隆任务重试",
                            "note": f"inbox={inbox['status']} task={related_task['status']}",
                        })
        outbox_stale = await self.db.fetch_all("""
            SELECT 'healthmind' AS schema_name, event_id, status, failure_code FROM healthmind.integration_outbox
             WHERE event_id::text=%s AND status IN ('failed', 'publishing')
            UNION ALL
            SELECT 'nutri', event_id, status, last_error FROM nutri.integration_outbox
             WHERE event_id::text=%s AND status IN ('failed', 'publishing')
        """, (query, query))
        for row in outbox_stale:
            suggestions.append({
                "operation": "reset_outbox", "schema_name": row["schema_name"],
                "record_id": str(row["event_id"]), "label": "重置滞留 outbox 为 pending",
                "note": f"{row['schema_name']} status={row['status']}",
            })
        attempts = await self.db.fetch_all("""
            SELECT a.attempt_id, a.task_id, a.status, a.started_at, a.timeout_ms, t.lock_version
              FROM healthmind.ai_task_attempts a
              JOIN healthmind.ai_tasks t USING (task_id)
             WHERE a.attempt_id::text=%s OR t.task_id::text=%s OR t.trace_id=%s
             ORDER BY a.created_at DESC LIMIT 5
        """, (query, query, query))
        if attempts:
            found["attempts"] = attempts
            for attempt in attempts:
                if attempt["status"] == "running" and attempt["started_at"]:
                    deadline = attempt["started_at"] + timedelta(milliseconds=attempt["timeout_ms"])
                    if deadline < datetime.now(UTC):
                        suggestions.append({
                            "operation": "recover_attempt", "schema_name": "healthmind",
                            "record_id": str(attempt["attempt_id"]),
                            "label": "恢复超时 attempt（自动重排或按耗尽发失败事件）",
                            "note": f"task {str(attempt['task_id'])[:12]}… lock_version={attempt['lock_version']}",
                            "expected_lock_version": str(attempt["lock_version"]),
                        })
        return {"query": query, "found": found, "suggestions": suggestions}
