import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from .database import Database
from .security import sha256_json


class Repository:
    def __init__(self, db: Database, stale_minutes: int, retention_days: int):
        self.db = db
        self.stale_minutes = stale_minutes
        self.retention_days = retention_days

    async def status(self) -> dict[str, Any]:
        if not self.db.pool:
            return {"database": {"ok": False, "error": self.db.schema_error}}
        tasks = await self.db.fetch_all("SELECT status, count(*)::int AS count FROM healthmind.ai_tasks GROUP BY status ORDER BY status")
        production = await self.db.fetch_one("""
            SELECT wr.*, tt.task_type_code,
              (SELECT count(*)::int FROM healthmind.workflow_release_tools rt WHERE rt.release_id=wr.release_id) AS tool_count
            FROM healthmind.workflow_releases wr JOIN healthmind.ai_task_types tt USING(task_type_id)
            WHERE wr.status='production' AND tt.task_type_code='nutrition.meal_analysis'
        """)
        failures = await self.db.fetch_all("""
            SELECT task_id, failure_code, failure_message, completed_at FROM healthmind.ai_tasks
            WHERE status='failed' ORDER BY completed_at DESC NULLS LAST LIMIT 8
        """)
        return {"database": {"ok": True, "write_enabled": self.db.write_enabled, "schema_error": self.db.schema_error},
                "tasks": tasks, "production": production, "recent_failures": failures}

    async def backlogs(self) -> dict[str, Any]:
        rows = await self.db.fetch_all("""
          SELECT 'healthmind.inbox' source,status,count(*)::int count FROM healthmind.integration_inbox GROUP BY status
          UNION ALL SELECT 'healthmind.outbox',status,count(*)::int FROM healthmind.integration_outbox GROUP BY status
          UNION ALL SELECT 'nutri.inbox',status,count(*)::int FROM nutri.integration_inbox GROUP BY status
          UNION ALL SELECT 'nutri.outbox',status,count(*)::int FROM nutri.integration_outbox GROUP BY status
          ORDER BY 1,2
        """)
        stale = await self.db.fetch_all("""
          SELECT 'task' source,task_id::text id,status,updated_at at FROM healthmind.ai_tasks
           WHERE status IN ('queued','running') AND updated_at < now()-(%s*interval '1 minute')
          UNION ALL
          SELECT 'healthmind.outbox',event_id::text,status,created_at FROM healthmind.integration_outbox
           WHERE status IN ('pending','publishing','failed') AND created_at < now()-(%s*interval '1 minute')
          UNION ALL
          SELECT 'nutri.outbox',event_id::text,status,created_at FROM nutri.integration_outbox
           WHERE status IN ('pending','publishing','failed') AND created_at < now()-(%s*interval '1 minute')
          ORDER BY at LIMIT 100
        """, (self.stale_minutes,) * 3)
        return {"counts": rows, "stale": stale}

    async def tasks(self, status: str | None, cursor: str | None, limit: int) -> list[dict[str, Any]]:
        clauses, params = [], []
        if status:
            clauses.append("t.status=%s"); params.append(status)
        if cursor:
            clauses.append("t.created_at < %s"); params.append(cursor)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(min(limit, 100))
        return await self.db.fetch_all(f"""
          SELECT t.*,tt.task_type_code,wr.release_version,
            (SELECT count(*)::int FROM healthmind.ai_task_attempts a WHERE a.task_id=t.task_id) attempt_count
          FROM healthmind.ai_tasks t JOIN healthmind.ai_task_types tt USING(task_type_id)
          JOIN healthmind.workflow_releases wr ON wr.release_id=t.workflow_release_id
          {where} ORDER BY t.created_at DESC LIMIT %s
        """, tuple(params))

    async def trace(self, value: str) -> dict[str, Any]:
        needle = f"%{value}%"
        queries = {
          "tasks": "SELECT * FROM healthmind.ai_tasks WHERE task_id::text=%s OR trace_id=%s OR aggregate_id=%s OR context_manifest::text ILIKE %s ORDER BY created_at",
          "attempts": "SELECT a.* FROM healthmind.ai_task_attempts a JOIN healthmind.ai_tasks t USING(task_id) WHERE a.attempt_id::text=%s OR t.task_id::text=%s OR t.trace_id=%s ORDER BY a.created_at",
          "tool_invocations": "SELECT i.* FROM healthmind.ai_tool_invocations i JOIN healthmind.ai_tasks t USING(task_id) WHERE i.task_id::text=%s OR i.attempt_id::text=%s OR i.trace_id=%s ORDER BY i.created_at",
          "healthmind_inbox": "SELECT * FROM healthmind.integration_inbox WHERE event_id::text=%s OR trace_id=%s OR aggregate_id=%s ORDER BY received_at",
          "healthmind_outbox": "SELECT * FROM healthmind.integration_outbox WHERE event_id::text=%s OR task_id::text=%s OR trace_id=%s OR aggregate_id=%s ORDER BY created_at",
          "nutri_outbox": "SELECT * FROM nutri.integration_outbox WHERE event_id::text=%s OR aggregate_id::text=%s OR payload::text ILIKE %s ORDER BY created_at",
          "nutri_inbox": "SELECT * FROM nutri.integration_inbox WHERE event_id::text=%s OR payload_sha256=%s ORDER BY created_at",
          "meals": "SELECT m.*,s.status capture_status FROM nutri.meal_records m JOIN nutri.meal_capture_sessions s USING(capture_session_id) WHERE m.meal_id::text=%s OR m.capture_session_id::text=%s ORDER BY m.created_at",
        }
        args = {
          "tasks": (value,value,value,needle), "attempts": (value,value,value), "tool_invocations": (value,value,value),
          "healthmind_inbox": (value,value,value), "healthmind_outbox": (value,value,value,value),
          "nutri_outbox": (value,value,needle), "nutri_inbox": (value,value), "meals": (value,value),
        }
        return {name: await self.db.fetch_all(sql, args[name]) for name, sql in queries.items()}

    async def releases(self) -> list[dict[str, Any]]:
        return await self.db.fetch_all("""
          SELECT wr.*,tt.task_type_code,
           COALESCE(jsonb_agg(jsonb_build_object('tool_code',td.tool_code,'scope',rt.allowed_scope)) FILTER(WHERE td.tool_id IS NOT NULL),'[]') tools
          FROM healthmind.workflow_releases wr JOIN healthmind.ai_task_types tt USING(task_type_id)
          LEFT JOIN healthmind.workflow_release_tools rt USING(release_id)
          LEFT JOIN healthmind.ai_tool_definitions td USING(tool_id)
          GROUP BY wr.release_id,tt.task_type_code ORDER BY wr.created_at DESC
        """)

    async def snapshot(self, table: str, column: str, value: str) -> dict[str, Any] | None:
        allowed = {
          ("healthmind.ai_tasks", "task_id"), ("healthmind.ai_task_attempts", "attempt_id"),
          ("healthmind.integration_outbox", "event_id"), ("nutri.integration_outbox", "event_id"),
          ("healthmind.workflow_releases", "release_id"),
        }
        if (table, column) not in allowed:
            raise ValueError("unsupported snapshot")
        return await self.db.fetch_one(f"SELECT * FROM {table} WHERE {column}=%s", (value,))

    async def create_release(self, data: dict[str, Any], reason: str) -> str:
        identity = "/".join(str(data[k]) for k in ("workspace_id","app_id","workflow_id","workflow_version"))
        rid = str(uuid5(NAMESPACE_URL, identity))
        async with self.db.transaction() as conn:
            cur = await conn.execute("SELECT task_type_id FROM healthmind.ai_task_types WHERE task_type_code=%s AND active", (data["task_type_code"],))
            tt = await cur.fetchone()
            if not tt: raise RuntimeError("active task type not found")
            await conn.execute("""INSERT INTO healthmind.workflow_releases
              (release_id,task_type_id,release_version,status,dify_workspace_id,dify_app_id,dify_workflow_id,dify_workflow_version,
               input_schema_version,input_schema,input_schema_sha256,output_schema_version,output_schema,output_schema_sha256,timeout_seconds,max_attempts)
              VALUES(%s,%s,%s,'candidate',%s,%s,%s,%s,'1.0',%s,%s,'1.0',%s,%s,120,1)""",
              (rid,tt["task_type_id"],data["release_version"],data["workspace_id"],data["app_id"],data["workflow_id"],data["workflow_version"],
               Jsonb(data["input_schema"]),sha256_json(data["input_schema"]),Jsonb(data["output_schema"]),sha256_json(data["output_schema"])))
            cur = await conn.execute("SELECT tool_id,auth_scope FROM healthmind.ai_tool_definitions WHERE active AND tool_code=ANY(%s)", (data["tool_codes"],))
            tools = await cur.fetchall()
            if len(tools) != len(data["tool_codes"]): raise RuntimeError("one or more active tool definitions are missing")
            for tool in tools:
                await conn.execute("INSERT INTO healthmind.workflow_release_tools(release_id,tool_id,allowed_scope,required,max_calls,timeout_ms) VALUES(%s,%s,%s,true,1,10000)", (rid,tool["tool_id"],tool["auth_scope"]))
            await conn.execute("INSERT INTO healthmind.workflow_release_audits(audit_id,release_id,action,to_status,reason) VALUES(%s,%s,'created','candidate',%s)", (uuid4(),rid,reason))
        return rid

    async def transition_release(self, rid: str, operation: str, reason: str) -> None:
        async with self.db.transaction() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('healthmind.workflow.production',0))")
            cur = await conn.execute("SELECT status,task_type_id FROM healthmind.workflow_releases WHERE release_id=%s FOR UPDATE", (rid,))
            release = await cur.fetchone()
            if not release: raise RuntimeError("release not found")
            old = release["status"]
            if operation in {"promote","rollback"}:
                await conn.execute("UPDATE healthmind.workflow_releases SET status='retired',retired_at=now() WHERE task_type_id=%s AND status='production' AND release_id<>%s", (release["task_type_id"],rid))
                await conn.execute("UPDATE healthmind.workflow_releases SET status='production',promoted_at=now(),retired_at=NULL WHERE release_id=%s", (rid,))
                new = "production"
            elif operation == "retire":
                await conn.execute("UPDATE healthmind.workflow_releases SET status='retired',retired_at=now() WHERE release_id=%s", (rid,)); new="retired"
            else: raise RuntimeError("unsupported transition")
            action = "rolled_back" if operation == "rollback" else ("promoted" if new == "production" else "retired")
            await conn.execute("INSERT INTO healthmind.workflow_release_audits(audit_id,release_id,action,from_status,to_status,reason) VALUES(%s,%s,%s,%s,%s,%s)", (uuid4(),rid,action,old,new,reason))

    async def retry_task(self, task_id: str, release_id: str | None, reason: str, operation_id: str) -> str:
        new_id = str(uuid4())
        async with self.db.transaction() as conn:
            cur = await conn.execute("SELECT * FROM healthmind.ai_tasks WHERE task_id=%s FOR UPDATE", (task_id,))
            old = await cur.fetchone()
            if not old or old["status"] not in ("failed","cancelled","expired"): raise RuntimeError("only terminal failed/cancelled/expired tasks can be cloned")
            selected = release_id
            if not selected:
                cur = await conn.execute("SELECT release_id FROM healthmind.workflow_releases WHERE task_type_id=%s AND status='production'", (old["task_type_id"],))
                row = await cur.fetchone(); selected = str(row["release_id"]) if row else None
            if not selected: raise RuntimeError("production release not found")
            manifest = dict(old["context_manifest"]); manifest.update(admin_retry_of_task_id=task_id, admin_operation_id=operation_id, admin_reason=reason)
            capture_id, meal_id = manifest.get("capture_session_id"), manifest.get("meal_id")
            cur = await conn.execute("""SELECT m.status,m.analysis_status,
              (SELECT count(*) FROM nutri.meal_capture_images i WHERE i.capture_session_id=m.capture_session_id AND i.status='confirmed') confirmed
              FROM nutri.meal_records m WHERE m.meal_id=%s AND m.capture_session_id=%s FOR UPDATE""", (meal_id,capture_id))
            meal = await cur.fetchone()
            if not meal or meal["status"] != "active" or meal["confirmed"] < 1: raise RuntimeError("active meal with confirmed images not found")
            await conn.execute("""INSERT INTO healthmind.ai_tasks
              (task_id,task_type_id,workflow_release_id,requester_service,subject_id,aggregate_type,aggregate_id,idempotency_key,
               invocation_mode,status,priority,trace_id,input_schema_version,input_digest,context_manifest,retention_until)
              SELECT %s,task_type_id,%s,'HealthMindControl',subject_id,aggregate_type,aggregate_id,%s,invocation_mode,'queued',priority,trace_id,
               (SELECT input_schema_version FROM healthmind.workflow_releases WHERE release_id=%s),input_digest,%s,now()+(%s*interval '1 day')
              FROM healthmind.ai_tasks WHERE task_id=%s""",
              (new_id,selected,f"admin-retry:{task_id}:{operation_id}",selected,Jsonb(manifest),self.retention_days,task_id))
            await conn.execute("UPDATE nutri.meal_records SET analysis_status='analysing' WHERE meal_id=%s AND analysis_status='failed'", (meal_id,))
            await conn.execute("UPDATE nutri.meal_capture_sessions SET status='analysing',failed_at=NULL WHERE capture_session_id=%s AND status='failed'", (capture_id,))
        return new_id

    async def recover(self, operation: str, schema: str, record_id: str) -> dict[str, Any]:
        async with self.db.transaction() as conn:
            if operation == "reset_outbox":
                if schema == "healthmind":
                    cur = await conn.execute("""UPDATE healthmind.integration_outbox SET status='pending',next_attempt_at=now(),published_at=NULL,failure_code=NULL,failure_message=NULL
                      WHERE event_id=%s AND status IN('failed','publishing') RETURNING event_id,status""", (record_id,))
                else:
                    cur = await conn.execute("""UPDATE nutri.integration_outbox SET status='pending',next_attempt_at=now(),published_at=NULL,last_error=NULL,locked_at=NULL
                      WHERE event_id=%s AND status IN('failed','publishing') RETURNING event_id,status""", (record_id,))
            elif operation == "cancel_task":
                cur = await conn.execute("""UPDATE healthmind.ai_tasks SET status='cancelled',completed_at=now(),lock_version=lock_version+1
                  WHERE task_id=%s AND status='queued' RETURNING task_id,status""", (record_id,))
            elif operation == "recover_attempt":
                cur = await conn.execute("""UPDATE healthmind.ai_task_attempts SET status='timed_out',finished_at=now(),failure_category='timeout',failure_code='ATTEMPT_TIMEOUT',failure_message='Recovered by HealthMindControl'
                  WHERE attempt_id=%s AND status='running' AND started_at+(timeout_ms*interval '1 millisecond')<now() RETURNING task_id,attempt_no""", (record_id,))
            else: raise RuntimeError("unsupported recovery")
            row = await cur.fetchone()
            if not row: raise RuntimeError("record changed or operation precondition failed")
            return dict(row)

