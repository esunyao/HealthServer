import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from ..security import sha256_json


class DebugService:
    HOLD_UNTIL = datetime(2099, 1, 1, tzinfo=UTC)

    def __init__(self, db, repo, kafka, dify, store, cfg):
        self.db, self.repo, self.kafka, self.dify = db, repo, kafka, dify
        self.store, self.cfg = store, cfg
        self.client = dify.client
        self._ephemeral: dict[str, dict[str, Any]] = {}

    async def users(self, query: str) -> list[dict[str, Any]]:
        term = f"%{query}%"
        return await self.db.fetch_all("""
          SELECT user_id, username, email, business_status AS status, created_at FROM orion.users
          WHERE user_id::text=%s OR username ILIKE %s OR COALESCE(email,'') ILIKE %s
          ORDER BY created_at DESC LIMIT 30
        """, (query, term, term))

    async def observe(self, run: dict[str, Any]) -> dict[str, Any]:
        context = run.get("context", {})
        values = [str(context.get(k, "")) for k in (
            "trace_id", "event_id", "task_id", "attempt_id", "meal_id", "capture_session_id"
        )]
        values = [v for v in values if v]
        if not values:
            return {"tables": {}}
        needle = values[0]
        tables: dict[str, Any] = {}
        tables["tasks"] = await self.db.fetch_all("""
          SELECT task_id,status,trace_id,request_event_id,aggregate_id,workflow_release_id,
                 scheduled_at,next_attempt_at,failure_code,created_at
          FROM healthmind.ai_tasks
          WHERE trace_id=%s OR task_id::text=%s OR request_event_id::text=%s OR aggregate_id=%s
          ORDER BY created_at DESC LIMIT 50
        """, (needle, needle, needle, needle))
        tables["attempts"] = await self.db.fetch_all("""
          SELECT a.* FROM healthmind.ai_task_attempts a JOIN healthmind.ai_tasks t USING(task_id)
          WHERE a.attempt_id::text=%s OR t.trace_id=%s OR t.task_id::text=%s
          ORDER BY a.created_at DESC LIMIT 50
        """, (needle, needle, needle))
        tables["healthmind_outbox"] = await self.db.fetch_all("""
          SELECT event_id,task_id,event_type,status,attempt_count,next_attempt_at,published_at,failure_code,trace_id,created_at
          FROM healthmind.integration_outbox WHERE event_id::text=%s OR trace_id=%s OR task_id::text=%s
          ORDER BY created_at DESC LIMIT 50
        """, (needle, needle, needle))
        tables["nutri_outbox"] = await self.db.fetch_all("""
          SELECT event_id,aggregate_id,event_type,status,attempt_count,next_attempt_at,published_at,last_error,created_at
          FROM nutri.integration_outbox WHERE event_id::text=%s OR aggregate_id::text=%s
          ORDER BY created_at DESC LIMIT 50
        """, (needle, needle))
        return {"run_id": run["run_id"], "observed_at": datetime.now(UTC), "tables": tables}

    async def preview_step(self, run: dict[str, Any], step: str, params: dict[str, Any]) -> dict[str, Any]:
        record_id = str(params.get("record_id") or run.get("context", {}).get(self._id_key(step), ""))
        if step in {"hold_capture", "release_capture"}:
            snapshot = await self.repo.snapshot("nutri.integration_outbox", "event_id", record_id)
        elif step in {"hold_task", "release_task"}:
            snapshot = await self.repo.snapshot("healthmind.ai_tasks", "task_id", record_id)
        elif step in {"hold_result", "release_result"}:
            snapshot = await self.repo.snapshot("healthmind.integration_outbox", "event_id", record_id)
        elif step == "kafka_capture":
            snapshot = await self.repo.snapshot("nutri.integration_outbox", "event_id", record_id)
        elif step == "emulate_hm_ingest":
            snapshot = await self.repo.snapshot("nutri.integration_outbox", "event_id", record_id)
        elif step in {"dify_run", "mcp_call"} or step.startswith("nutri_"):
            endpoint = self.cfg.dify_url if step == "dify_run" else self.cfg.mcp_url
            if step.startswith("nutri_"):
                endpoint = self.cfg.nutri_api_url
                if not endpoint:
                    raise ValueError("HMC_NUTRI_API_URL is not configured")
            snapshot = {"endpoint": endpoint,
                        "credentials": "ephemeral; never persisted"}
        else:
            raise ValueError("unsupported debug step")
        if not snapshot:
            raise ValueError("target record not found")
        return {"step": step, "record_id": record_id, "params": params, "snapshot": snapshot}

    async def execute_step(self, run: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
        step, record_id, params = intent["step"], intent["record_id"], intent["params"]
        if step in {"hold_capture", "release_capture", "hold_result", "release_result", "hold_task", "release_task"}:
            result = await self._schedule(step, record_id)
        elif step == "kafka_capture":
            message = await self.repo.hm_capture_ready_message(record_id)
            result = await self.kafka.produce(
                message["topic"], message["key"], message["payload"],
                {"x-hmc-debug-run": run["run_id"]}, None,
            )
        elif step == "emulate_hm_ingest":
            result = await self._emulate_hm_ingest(run["run_id"], record_id)
        elif step.startswith("nutri_"):
            result = await self._nutri(step, params, run["run_id"])
        elif step == "dify_run":
            result = await self._dify_run(params)
        elif step == "mcp_call":
            result = await self._mcp_call(params)
        else:
            raise ValueError("unsupported debug step")
        patch = {self._id_key(step): record_id} if record_id else {}
        if isinstance(result, dict):
            for key in ("task_id", "attempt_id", "event_id", "trace_id", "workflow_run_id"):
                if result.get(key) is not None:
                    patch[key] = str(result[key])
            data = result.get("data") if isinstance(result.get("data"), dict) else result
            for source, target in (("captureSessionId", "capture_session_id"), ("imageId", "image_id"),
                                   ("mealId", "meal_id")):
                if data.get(source) is not None:
                    patch[target] = data[source]
            if isinstance(data.get("captureSession"), dict):
                patch["capture_session_id"] = data["captureSession"].get("captureSessionId")
            if isinstance(data.get("meal"), dict):
                patch["meal_id"] = data["meal"].get("mealId")
        if patch:
            await asyncio.to_thread(self.store.update_context, run["run_id"], patch)
        return result

    async def _schedule(self, step: str, record_id: str) -> dict[str, Any]:
        hold = step.startswith("hold_")
        when = self.HOLD_UNTIL if hold else datetime.now(UTC)
        async with self.db.transaction() as conn:
            if step.endswith("capture"):
                cur = await conn.execute(
                    "UPDATE nutri.integration_outbox SET next_attempt_at=%s, locked_at=NULL "
                    "WHERE event_id=%s AND status IN ('pending','failed') RETURNING event_id,status,next_attempt_at",
                    (when, record_id),
                )
            elif step.endswith("result"):
                cur = await conn.execute(
                    "UPDATE healthmind.integration_outbox SET next_attempt_at=%s "
                    "WHERE event_id=%s AND status IN ('pending','failed') RETURNING event_id,status,next_attempt_at",
                    (when, record_id),
                )
            else:
                cur = await conn.execute(
                    "UPDATE healthmind.ai_tasks SET scheduled_at=%s,next_attempt_at=%s,lock_version=lock_version+1 "
                    "WHERE task_id=%s AND status='queued' RETURNING task_id,status,scheduled_at,lock_version",
                    (when, when, record_id),
                )
            row = await cur.fetchone()
            if not row:
                raise RuntimeError("record changed or stage precondition failed")
            return dict(row)

    async def _emulate_hm_ingest(self, run_id: str, event_id: str) -> dict[str, Any]:
        """Mirror HealthMind's capture listener transaction for controlled consumer isolation."""
        async with self.db.transaction() as conn:
            cur = await conn.execute(
                "SELECT payload,status FROM nutri.integration_outbox WHERE event_id=%s FOR UPDATE", (event_id,),
            )
            source = await cur.fetchone()
            if not source:
                raise RuntimeError("capture-ready source event not found")
            envelope = source["payload"]
            payload = envelope.get("payload", {})
            cur = await conn.execute("""SELECT tt.task_type_id,wr.release_id,wr.input_schema_version
              FROM healthmind.ai_task_types tt JOIN healthmind.workflow_releases wr USING(task_type_id)
              WHERE tt.task_type_code='nutrition.meal_analysis' AND tt.active AND wr.status='production'""")
            release = await cur.fetchone()
            if not release:
                raise RuntimeError("production release not found")
            task_id = str(uuid4())
            digest = sha256_json(envelope)
            inserted = await conn.execute("""INSERT INTO healthmind.integration_inbox
              (event_id,event_type,schema_version,producer,subject_id,aggregate_type,aggregate_id,
               trace_id,payload_sha256,status,processed_at,retention_until)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'processed',now(),now()+interval '30 days')
              ON CONFLICT(event_id) DO NOTHING""",
              (event_id, envelope["event_type"], envelope["schema_version"], envelope["producer"],
               envelope.get("subject_id"), envelope["aggregate_type"], str(envelope["aggregate_id"]),
               envelope["trace_id"], digest))
            if inserted.rowcount != 1:
                raise RuntimeError("HealthMind inbox already exists; use the real task or clone retry")
            manifest = {"capture_session_id": payload.get("capture_session_id"), "meal_id": payload.get("meal_id"),
                        "hmc_debug_run_id": run_id}
            await conn.execute("""INSERT INTO healthmind.ai_tasks
              (task_id,task_type_id,workflow_release_id,request_event_id,requester_service,subject_id,
               aggregate_type,aggregate_id,idempotency_key,status,trace_id,input_schema_version,input_digest,
               context_manifest,scheduled_at,next_attempt_at,retention_until)
              VALUES (%s,%s,%s,%s,'HealthMindControl',%s,%s,%s,%s,'queued',%s,%s,%s,%s,%s,%s,
                      now()+interval '180 days')""",
              (task_id, release["task_type_id"], release["release_id"], event_id, envelope.get("subject_id"),
               envelope["aggregate_type"], str(envelope["aggregate_id"]), f"hmc:{run_id}:{event_id}",
               envelope["trace_id"], release["input_schema_version"], digest, Jsonb(manifest),
               self.HOLD_UNTIL, self.HOLD_UNTIL))
            return {"task_id": task_id, "event_id": event_id, "trace_id": envelope["trace_id"],
                    "status": "queued", "held": True, "release_id": str(release["release_id"])}

    async def _dify_run(self, params: dict[str, Any]) -> dict[str, Any]:
        token = str(params.get("app_api_key", ""))
        if not token:
            raise ValueError("app_api_key is required and is never persisted")
        payload = {"inputs": params.get("inputs", {}), "response_mode": "blocking",
                   "user": str(params.get("user", "HealthMindControl"))}
        response = await self.client.post(
            f"{self.cfg.dify_url.rstrip('/')}/v1/workflows/run", json=payload,
            headers={"Authorization": f"Bearer {token}"}, timeout=180,
        )
        response.raise_for_status()
        return response.json()

    async def _nutri(self, step: str, params: dict[str, Any], run_id: str) -> dict[str, Any]:
        bearer = str(params.get("bearer", ""))
        if not bearer and step != "nutri_upload":
            raise ValueError("bearer is required and is never persisted")
        base = self.cfg.nutri_api_url.rstrip("/") + "/v1/nutri"
        headers = {"Authorization": f"Bearer {bearer}"}
        client = self.client
        if step == "nutri_create":
            headers["X-Idempotency-Key"] = str(params.get("client_request_id") or uuid4())
            response = await client.post(f"{base}/capture-sessions", headers=headers,
                                         json={"timezone": params.get("timezone", "Asia/Shanghai")})
        elif step == "nutri_presign":
            sid = self._required(params, "capture_session_id")
            response = await client.post(f"{base}/capture-sessions/{sid}/images/presign", headers=headers,
                                         json={"fileName": self._required(params, "file_name"),
                                               "contentType": params.get("content_type", "image/jpeg"),
                                               "contentLength": int(self._required(params, "content_length")),
                                               "capturedAt": params.get("captured_at")})
        elif step == "nutri_upload":
            ephemeral = self._ephemeral.get(run_id, {})
            upload_url = params.get("upload_url") or ephemeral.get("upload_url")
            upload_url = self._required({"upload_url": upload_url}, "upload_url")
            file_path = Path(self._required(params, "file_path"))
            if not file_path.is_file():
                raise ValueError("file_path does not point to a file")
            if file_path.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("image exceeds 10 MiB")
            raw_headers = params.get("upload_headers") or ephemeral.get("upload_headers", {})
            upload_headers = {str(k): str(v) for k, v in raw_headers.items()}
            response = await client.put(upload_url, headers=upload_headers, content=file_path.read_bytes())
            response.raise_for_status()
            return {"status": response.status_code, "uploaded_bytes": file_path.stat().st_size}
        elif step == "nutri_confirm":
            sid, image_id = self._required(params, "capture_session_id"), self._required(params, "image_id")
            response = await client.post(f"{base}/capture-sessions/{sid}/images/{image_id}/confirm", headers=headers)
        elif step == "nutri_submit":
            sid = self._required(params, "capture_session_id")
            response = await client.post(f"{base}/capture-sessions/{sid}/submit", headers=headers,
                                         json={"mealType": params.get("meal_type", "other"),
                                               "notes": params.get("notes")})
        else:
            raise ValueError("unsupported Nutri step")
        response.raise_for_status()
        result = response.json()
        if step == "nutri_presign":
            data = result.get("data", {}) if isinstance(result, dict) else {}
            self._ephemeral[run_id] = {
                "upload_url": data.get("uploadUrl"), "upload_headers": data.get("requiredHeaders", {}),
            }
        return result

    async def _mcp_call(self, params: dict[str, Any]) -> dict[str, Any]:
        bearer = str(params.get("bearer", ""))
        method = str(params.get("method", "tools/list"))
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params.get("arguments", {})}
        headers = {"Accept": "application/json, text/event-stream"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        response = await self.client.post(self.cfg.mcp_url, json=payload, headers=headers, timeout=60)
        return {"status": response.status_code, "body": response.text[:100_000]}

    @staticmethod
    def _id_key(step: str) -> str:
        if step.startswith("nutri_"):
            return "capture_session_id"
        if "capture" in step:
            return "event_id"
        if "task" in step:
            return "task_id"
        if "result" in step:
            return "result_event_id"
        return "record_id"

    @staticmethod
    def _required(params: dict[str, Any], key: str) -> Any:
        value = params.get(key)
        if value is None or value == "":
            raise ValueError(f"{key} is required")
        return value
