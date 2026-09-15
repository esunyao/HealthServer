import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from psycopg import sql
from psycopg.types.json import Jsonb

from ..security import sha256_json


HOLD_UNTIL = "2099-01-01T00:00:00+00:00"
MCP_TOOL_CODES = ("nutrimemo.capture_context.get", "orion.nutrition_context.get")

# 这里只开放运行期数据。任务类型、release、工具定义等配置表继续由专用页面管理。
FIXTURE_TABLES: dict[str, tuple[str, ...]] = {
    "healthmind.integration_inbox": ("event_id",),
    "healthmind.ai_tasks": ("task_id",),
    "healthmind.ai_task_attempts": ("attempt_id",),
    "healthmind.ai_tool_invocations": ("invocation_id",),
    "healthmind.ai_task_results": ("result_id",),
    "healthmind.ai_task_artifacts": ("artifact_id",),
    "healthmind.integration_outbox": ("event_id",),
    "nutri.integration_inbox": ("event_id",),
    "nutri.integration_outbox": ("event_id",),
    "nutri.meal_capture_sessions": ("capture_session_id",),
    "nutri.meal_capture_images": ("image_id",),
    "nutri.meal_records": ("meal_id",),
    "nutri.meal_items": ("item_id",),
    "nutri.meal_item_nutrient_values": ("item_id", "nutrient_id"),
    "nutri.meal_nutrition_values": ("meal_id", "nutrient_id"),
    "nutri.daily_nutrition_summaries": ("summary_id",),
    "nutri.daily_nutrition_values": ("summary_id", "nutrient_id"),
}


def _path_get(source: dict[str, Any], path: str | None) -> Any:
    if not path:
        return None
    current: Any = source
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def resolve_fixture_mappings(mappings: dict[str, Any], source: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """将 UI 字段映射解析为冻结值；execute 只使用预览阶段得到的冻结值。"""
    resolved: dict[str, Any] = {}
    instant = now or datetime.now(UTC)
    deferred: list[tuple[str, dict[str, Any]]] = []
    for column, raw in mappings.items():
        item = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
        mode = item.get("mode", "omit")
        if mode == "omit":
            continue
        if mode in {"inherit", "related"}:
            value = _path_get(source, item.get("source_field") or column)
        elif mode == "manual":
            value = item.get("value")
        elif mode == "generate":
            generator = item.get("generator")
            if generator == "uuid":
                value = str(uuid4())
            elif generator == "now":
                value = instant.isoformat()
            elif generator == "hold_until":
                value = HOLD_UNTIL
            elif generator == "retention_until":
                value = (instant + timedelta(days=180)).isoformat()
            elif generator == "sha256":
                deferred.append((column, item))
                continue
            else:
                raise ValueError(f"字段 {column} 的生成器无效")
        else:
            raise ValueError(f"字段 {column} 的映射模式无效")
        resolved[column] = value
    for column, item in deferred:
        ref = item.get("source_field")
        value = resolved.get(ref.removeprefix("$") if ref and ref.startswith("$") else "")
        if value is None:
            value = _path_get(source, ref) if ref else source
        resolved[column] = sha256_json(value)
    return resolved


class FixturesMixin:
    """白名单数据构造器与 MCP 调试 task/attempt 生命周期。"""

    async def fixture_tables(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch_all("""
            SELECT table_schema||'.'||table_name AS table_name, column_name, ordinal_position,
                   data_type, udt_name, is_nullable='YES' AS nullable, column_default,
                   is_identity='YES' AS identity, is_generated<>'NEVER' AS generated
              FROM information_schema.columns
             WHERE table_schema IN ('healthmind','nutri')
             ORDER BY table_schema,table_name,ordinal_position
        """)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if row["table_name"] in FIXTURE_TABLES:
                grouped.setdefault(row["table_name"], []).append(row)
        constraints = await self.db.fetch_all("""
            SELECT n.nspname||'.'||t.relname AS table_name, c.conname,
                   CASE c.contype WHEN 'p' THEN 'primary' WHEN 'f' THEN 'foreign'
                        WHEN 'u' THEN 'unique' WHEN 'c' THEN 'check' ELSE c.contype::text END AS kind,
                   pg_get_constraintdef(c.oid) AS definition
              FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
              JOIN pg_namespace n ON n.oid=t.relnamespace
             WHERE n.nspname IN ('healthmind','nutri')
        """)
        by_constraint: dict[str, list[dict[str, Any]]] = {}
        for row in constraints:
            if row["table_name"] in FIXTURE_TABLES:
                by_constraint.setdefault(row["table_name"], []).append(row)
        return [{
            "table_name": name, "primary_key": list(FIXTURE_TABLES[name]),
            "columns": grouped.get(name, []), "constraints": by_constraint.get(name, []),
            "operations": ["insert", "update"],
        } for name in FIXTURE_TABLES]

    async def fixture_table(self, table_name: str) -> dict[str, Any]:
        if table_name not in FIXTURE_TABLES:
            raise ValueError("目标表不在数据构造白名单中")
        tables = await self.fixture_tables()
        table = next((item for item in tables if item["table_name"] == table_name), None)
        if not table or not table["columns"]:
            raise RuntimeError(f"数据库中不存在 {table_name} 或字段不可见")
        return table

    async def fixture_source(self, identifier: str) -> dict[str, Any]:
        """把任意常用业务 ID 解析回任务链，并提供可用于字段映射的扁平/分组数据。"""
        task_id: Any = None
        is_uuid = False
        try:
            UUID(identifier)
            is_uuid = True
            row = await self.db.fetch_one("SELECT task_id FROM healthmind.ai_tasks WHERE task_id=%s", (identifier,))
            if not row:
                row = await self.db.fetch_one(
                    "SELECT task_id FROM healthmind.ai_task_attempts WHERE attempt_id=%s", (identifier,),
                )
            if not row:
                row = await self.db.fetch_one(
                    "SELECT task_id FROM healthmind.integration_outbox WHERE event_id=%s", (identifier,),
                )
            if not row:
                row = await self.db.fetch_one(
                    "SELECT task_id FROM healthmind.ai_tasks WHERE request_event_id=%s ORDER BY created_at DESC LIMIT 1",
                    (identifier,),
                )
            task_id = row["task_id"] if row else None
        except ValueError:
            pass
        if task_id is None:
            row = await self.db.fetch_one("""
                SELECT task_id FROM healthmind.ai_tasks
                 WHERE trace_id=%s OR aggregate_id=%s OR context_manifest->>'meal_id'=%s
                 ORDER BY created_at DESC LIMIT 1
            """, (identifier, identifier, identifier))
            task_id = row["task_id"] if row else None
        if task_id is not None:
            bundle = await self.task_bundle(str(task_id))
            task = bundle.get("task")
            if not task:
                raise RuntimeError("任务不存在")
            latest_attempt = bundle["attempts"][-1] if bundle.get("attempts") else {}
            result = bundle["results"][-1] if bundle.get("results") else {}
            # task_bundle 为详情页刻意省略 payload；数据构造器必须读取完整源 outbox。
            latest_outbox = await self.db.fetch_one(
                "SELECT * FROM healthmind.integration_outbox WHERE task_id=%s ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            ) or {}
            grouped = {
                "task": task, "attempt": latest_attempt, "result": result,
                "outbox": latest_outbox, "meal": bundle.get("meal") or {},
                "context": task.get("context_manifest") or {},
            }
            return self._fixture_source_document(
                identifier, "healthmind.ai_tasks", "task_id", str(task_id), grouped,
            )

        # 尚未生成 AI task 的事件/餐食也可以作为构造模板。
        candidates = (
            ("healthmind.integration_inbox", "event_id"),
            ("nutri.integration_outbox", "event_id"),
            ("nutri.integration_inbox", "event_id"),
            ("nutri.meal_capture_sessions", "capture_session_id"),
        )
        for table, key in (candidates if is_uuid else ()):
            row = await self.db.fetch_one(f"SELECT * FROM {table} WHERE {key}=%s", (identifier,))
            if row:
                grouped = {"event" if "integration_" in table else "capture": row}
                payload = row.get("payload")
                if isinstance(payload, dict):
                    grouped["event_payload"] = payload
                    if isinstance(payload.get("payload"), dict):
                        grouped["payload"] = payload["payload"]
                capture_id = row.get("aggregate_id") if table == "nutri.integration_outbox" else row.get("capture_session_id")
                if capture_id:
                    meal = await self.db.fetch_one(
                        "SELECT * FROM nutri.meal_records WHERE capture_session_id=%s", (capture_id,),
                    )
                    if meal:
                        grouped["meal"] = meal
                return self._fixture_source_document(identifier, table, key, identifier, grouped)
        if identifier.isdigit():
            meal = await self.db.fetch_one("SELECT * FROM nutri.meal_records WHERE meal_id=%s", (int(identifier),))
            if meal:
                capture = await self.db.fetch_one(
                    "SELECT * FROM nutri.meal_capture_sessions WHERE capture_session_id=%s",
                    (meal["capture_session_id"],),
                ) or {}
                return self._fixture_source_document(
                    identifier, "nutri.meal_records", "meal_id", identifier,
                    {"meal": meal, "capture": capture},
                )
        raise RuntimeError("未从该标识找到任务、事件、餐食或采集会话")

    @staticmethod
    def _fixture_source_document(identifier: str, table: str, anchor_key: str, anchor_value: str,
                                 grouped: dict[str, Any]) -> dict[str, Any]:
        flat: dict[str, Any] = {}
        for section in grouped.values():
            if isinstance(section, dict):
                for field, field_value in section.items():
                    flat.setdefault(field, field_value)
        return {
            "identifier": identifier,
            "anchor": {"table": table, "key": anchor_key, "value": str(anchor_value)},
            "records": grouped, "flat": flat,
        }

    async def fixture_source_snapshot(self, identifier: str | None) -> dict[str, Any]:
        if not identifier:
            return {}
        source = await self.fixture_source(identifier)
        anchor = source["anchor"]
        return await self.db.fetch_one(
            f"SELECT * FROM {anchor['table']} WHERE {anchor['key']}=%s", (anchor["value"],),
        ) or {}

    async def fixture_draft(self, table_name: str, identifier: str | None) -> dict[str, Any]:
        table = await self.fixture_table(table_name)
        source = await self.fixture_source(identifier) if identifier else {"records": {}, "flat": {}}
        flat = source["flat"]
        mappings: dict[str, dict[str, Any]] = {}
        pk = set(table["primary_key"])
        for column in table["columns"]:
            name, udt = column["column_name"], column["udt_name"]
            item: dict[str, Any] = {"mode": "omit"}
            if name in pk and udt == "uuid":
                item = {"mode": "generate", "generator": "uuid"}
            elif name in flat and flat[name] is not None:
                item = {"mode": "inherit", "source_field": f"flat.{name}"}
            elif name in {"created_at", "updated_at", "received_at"} and column["column_default"]:
                item = {"mode": "omit"}
            elif not column["nullable"] and column["column_default"] is None and name not in pk:
                item = {"mode": "manual", "value": None}
            mappings[name] = item
        if table_name.endswith("integration_outbox"):
            mappings["next_attempt_at"] = {"mode": "generate", "generator": "hold_until"}
            mappings["status"] = {"mode": "manual", "value": "pending"}
        if "retention_until" in mappings:
            mappings["retention_until"] = {"mode": "generate", "generator": "retention_until"}
        for digest, payload in (("payload_sha256", "payload"), ("result_sha256", "result_payload")):
            if digest in mappings:
                mappings[digest] = {"mode": "generate", "generator": "sha256", "source_field": f"${payload}"}
        if table_name == "healthmind.ai_tasks":
            mappings.update({
                "request_event_id": {"mode": "omit"},
                "requester_service": {"mode": "manual", "value": "HealthMindControl"},
                "idempotency_key": {"mode": "generate", "generator": "uuid"},
                "status": {"mode": "manual", "value": "queued"},
                "scheduled_at": {"mode": "generate", "generator": "hold_until"},
                "next_attempt_at": {"mode": "generate", "generator": "hold_until"},
                "started_at": {"mode": "omit"}, "completed_at": {"mode": "omit"},
                "failure_code": {"mode": "omit"}, "failure_message": {"mode": "omit"},
                "lock_version": {"mode": "manual", "value": 0},
            })
        elif table_name == "healthmind.ai_task_attempts":
            mappings["task_id"] = {"mode": "related", "source_field": "task.task_id"}
            attempt = source.get("records", {}).get("attempt", {})
            next_attempt = int(attempt.get("attempt_no") or 0) + 1
            mappings["attempt_no"] = {"mode": "manual", "value": next_attempt}
            mappings["status"] = {"mode": "manual", "value": "pending"}
            mappings["started_at"] = {"mode": "omit"}
            mappings["finished_at"] = {"mode": "omit"}
        elif table_name == "healthmind.ai_task_results":
            mappings["task_id"] = {"mode": "related", "source_field": "task.task_id"}
            mappings["result_payload"] = {"mode": "manual", "value": {}}
            mappings["produced_at"] = {"mode": "generate", "generator": "now"}
            mappings["expires_at"] = {"mode": "generate", "generator": "retention_until"}
        elif table_name == "nutri.integration_outbox":
            mappings["aggregate_id"] = {"mode": "related", "source_field": "context.capture_session_id"}
        return {"table": table, "source": source, "mappings": mappings}

    @staticmethod
    def _normalize_value(meta: dict[str, Any], value: Any) -> Any:
        if value is None:
            return None
        udt = meta["udt_name"]
        if udt in {"json", "jsonb"}:
            parsed = json.loads(value) if isinstance(value, str) else value
            return Jsonb(parsed)
        if udt in {"int2", "int4", "int8"}:
            return int(value)
        if udt in {"numeric", "float4", "float8"}:
            return Decimal(str(value))
        if udt == "bool" and isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return value

    async def _prepared_values(self, table_name: str, mappings: dict[str, Any], source_identifier: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
        table = await self.fixture_table(table_name)
        source = await self.fixture_source(source_identifier) if source_identifier else {"records": {}, "flat": {}}
        mapping_source = {**source.get("records", {}), "flat": source.get("flat", {})}
        raw = resolve_fixture_mappings(mappings, mapping_source)
        metas = {item["column_name"]: item for item in table["columns"]}
        unknown = sorted(set(raw) - set(metas))
        if unknown:
            raise ValueError("未知或不可写字段: " + ", ".join(unknown))
        values = {name: self._normalize_value(metas[name], value) for name, value in raw.items()}
        return values, source

    @staticmethod
    def _table_identifier(table_name: str) -> sql.Identifier:
        schema, table = table_name.split(".", 1)
        return sql.Identifier(schema, table)

    async def _mutate_fixture(self, conn: Any, operation: str, table_name: str,
                              values: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        if not values:
            raise ValueError("没有选择任何写入字段")
        if operation == "insert":
            names = list(values)
            query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
                self._table_identifier(table_name),
                sql.SQL(",").join(map(sql.Identifier, names)),
                sql.SQL(",").join(sql.Placeholder() for _ in names),
            )
            cur = await conn.execute(query, tuple(values[name] for name in names))
        else:
            primary = FIXTURE_TABLES[table_name]
            if set(target) != set(primary):
                raise ValueError("更新操作必须提供完整主键: " + ", ".join(primary))
            illegal = set(values) & set(primary)
            if illegal:
                raise ValueError("更新时不能修改主键: " + ", ".join(sorted(illegal)))
            assignments = sql.SQL(",").join(
                sql.SQL("{}={}").format(sql.Identifier(name), sql.Placeholder()) for name in values
            )
            predicates = sql.SQL(" AND ").join(
                sql.SQL("{}={}").format(sql.Identifier(name), sql.Placeholder()) for name in primary
            )
            query = sql.SQL("UPDATE {} SET {} WHERE {} RETURNING *").format(
                self._table_identifier(table_name), assignments, predicates,
            )
            params = tuple(values.values()) + tuple(target[name] for name in primary)
            cur = await conn.execute(query, params)
        row = await cur.fetchone()
        if not row:
            raise RuntimeError("目标记录不存在或写入条件不成立")
        return dict(row)

    async def preview_fixture(self, operation: str, table_name: str, source_identifier: str | None,
                              target: dict[str, Any], mappings: dict[str, Any]) -> dict[str, Any]:
        values, _ = await self._prepared_values(table_name, mappings, source_identifier)
        if operation == "insert" and table_name in {"healthmind.ai_tasks", "healthmind.ai_task_attempts"}:
            metadata_field = "context_manifest" if table_name.endswith("ai_tasks") else "execution_metadata"
            current = values.get(metadata_field)
            metadata = dict(current.obj) if isinstance(current, Jsonb) and isinstance(current.obj, dict) else {}
            metadata.update({"hmc_fixture": True, "hmc_source_identifier": source_identifier})
            values[metadata_field] = Jsonb(metadata)
        warnings: list[str] = []
        if table_name.endswith("integration_outbox") and values.get("status", "pending") in {"pending", "failed"}:
            if str(values.get("next_attempt_at")) != HOLD_UNTIL:
                warnings.append("该 outbox 到期后可能被真实发布器领取；建议使用 hold_until")
        async with self.db.preview_transaction() as conn:
            result = await self._mutate_fixture(conn, operation, table_name, values, target)
        frozen = {key: (value.obj if isinstance(value, Jsonb) else value) for key, value in values.items()}
        return {"values": frozen, "result": result, "warnings": warnings}

    async def execute_fixture(self, operation: str, table_name: str, values: dict[str, Any],
                              target: dict[str, Any]) -> dict[str, Any]:
        table = await self.fixture_table(table_name)
        metas = {item["column_name"]: item for item in table["columns"]}
        normalized = {name: self._normalize_value(metas[name], value) for name, value in values.items()}
        async with self.db.transaction() as conn:
            return await self._mutate_fixture(conn, operation, table_name, normalized, target)

    async def fixture_target_snapshot(self, table_name: str, target: dict[str, Any]) -> dict[str, Any]:
        if not target:
            return {}
        primary = FIXTURE_TABLES.get(table_name)
        if not primary or set(target) != set(primary):
            raise ValueError("目标主键不完整")
        predicates = sql.SQL(" AND ").join(
            sql.SQL("{}={}").format(sql.Identifier(name), sql.Placeholder()) for name in primary
        )
        query = sql.SQL("SELECT * FROM {} WHERE {}").format(self._table_identifier(table_name), predicates)
        if not self.db.pool:
            return {}
        async with self.db.pool.connection() as conn:
            cur = await conn.execute(query, tuple(target[name] for name in primary))
            row = await cur.fetchone()
        return dict(row) if row else {}

    async def prepare_mcp_session(self, source_task_id: str, inherit_trace_id: bool,
                                  lease_minutes: int) -> dict[str, Any]:
        source = await self.db.fetch_one("SELECT * FROM healthmind.ai_tasks WHERE task_id=%s", (source_task_id,))
        if not source:
            raise RuntimeError("源任务不存在")
        context = source.get("context_manifest") or {}
        capture_id, meal_id = context.get("capture_session_id"), context.get("meal_id")
        try:
            UUID(str(capture_id))
            meal_id = int(meal_id)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("源任务缺少有效的 capture_session_id 或 meal_id，无法构造可读取的 MCP 任务") from exc
        meal = await self.db.fetch_one("""
            SELECT m.status AS meal_status,s.status AS capture_status,
                   (SELECT count(*)::int FROM nutri.meal_capture_images i
                     WHERE i.capture_session_id=m.capture_session_id AND i.status='confirmed') AS confirmed_images
              FROM nutri.meal_records m JOIN nutri.meal_capture_sessions s USING(capture_session_id)
             WHERE m.meal_id=%s AND m.capture_session_id=%s
        """, (meal_id, str(capture_id)))
        if not meal:
            raise RuntimeError("源任务关联的餐食或采集会话不存在")
        if meal["meal_status"] != "active" or int(meal["confirmed_images"] or 0) < 1:
            raise RuntimeError("MCP 测试要求 active 餐食且至少存在一张 confirmed 图片")
        bindings = await self.db.fetch_all("""
            SELECT d.tool_code,rt.allowed_scope,rt.max_calls
              FROM healthmind.workflow_release_tools rt
              JOIN healthmind.ai_tool_definitions d USING(tool_id)
             WHERE rt.release_id=%s AND d.active
        """, (source["workflow_release_id"],))
        found = {row["tool_code"] for row in bindings}
        missing = [code for code in MCP_TOOL_CODES if code not in found]
        if missing:
            raise RuntimeError("该任务 release 未绑定 MCP 工具: " + ", ".join(missing))
        now = datetime.now(UTC)
        lease_until = now + timedelta(minutes=lease_minutes)
        task_id, attempt_id, session_id = str(uuid4()), str(uuid4()), str(uuid4())
        manifest = dict(source.get("context_manifest") or {})
        manifest.update({
            "hmc_mcp_session": True, "hmc_session_id": session_id,
            "hmc_source_task_id": source_task_id, "hmc_lease_until": lease_until.isoformat(),
        })
        data = {
            "task_id": task_id, "attempt_id": attempt_id,
            "trace_id": source["trace_id"] if inherit_trace_id else str(uuid4()),
            "session_id": session_id, "lease_until": lease_until.isoformat(),
            "source_task_id": source_task_id, "source": source, "manifest": manifest,
            "bindings": bindings,
        }
        async with self.db.preview_transaction() as conn:
            await self._insert_mcp_session(conn, data)
        return data

    async def _insert_mcp_session(self, conn: Any, data: dict[str, Any]) -> None:
        source = data["source"]
        await conn.execute("""INSERT INTO healthmind.ai_tasks
          (task_id,task_type_id,workflow_release_id,requester_service,subject_id,aggregate_type,aggregate_id,
           idempotency_key,invocation_mode,status,priority,trace_id,input_schema_version,input_digest,
           context_manifest,scheduled_at,deadline_at,next_attempt_at,started_at,retention_until)
          VALUES (%s,%s,%s,'HealthMindControl',%s,%s,%s,%s,'sync','running',%s,%s,%s,%s,%s,
                  now(),%s,now(),now(),now()+(%s*interval '1 day'))""",
          (data["task_id"], source["task_type_id"], source["workflow_release_id"], source["subject_id"],
           source["aggregate_type"], source["aggregate_id"], f"hmc-mcp:{data['session_id']}",
           source["priority"], data["trace_id"], source["input_schema_version"], source["input_digest"],
           Jsonb(data["manifest"]), data["lease_until"], self.retention_days))
        metadata = {"hmc_mcp_session": True, "hmc_session_id": data["session_id"],
                    "hmc_lease_until": data["lease_until"]}
        await conn.execute("""INSERT INTO healthmind.ai_task_attempts
          (attempt_id,task_id,attempt_no,status,started_at,timeout_ms,execution_metadata)
          VALUES (%s,%s,1,'running',now(),3600000,%s)""",
          (data["attempt_id"], data["task_id"], Jsonb(metadata)))

    async def create_mcp_session(self, data: dict[str, Any]) -> dict[str, Any]:
        source = await self.db.fetch_one("SELECT * FROM healthmind.ai_tasks WHERE task_id=%s", (data["source_task_id"],))
        if not source:
            raise RuntimeError("源任务不存在")
        frozen = dict(data)
        frozen["source"] = source
        async with self.db.transaction() as conn:
            await self._insert_mcp_session(conn, frozen)
        return {key: frozen[key] for key in ("task_id", "attempt_id", "trace_id", "session_id", "lease_until")}

    async def mcp_session(self, task_id: str) -> dict[str, Any] | None:
        return await self.db.fetch_one("""
            SELECT t.task_id,t.trace_id,t.status,t.started_at,t.deadline_at,t.context_manifest,
                   a.attempt_id,a.status AS attempt_status,a.started_at AS attempt_started_at,
                   a.timeout_ms,a.execution_metadata
              FROM healthmind.ai_tasks t JOIN healthmind.ai_task_attempts a USING(task_id)
             WHERE t.task_id=%s AND t.context_manifest->>'hmc_mcp_session'='true'
             ORDER BY a.attempt_no DESC LIMIT 1
        """, (task_id,))

    async def renew_mcp_session(self, task_id: str, lease_minutes: int) -> dict[str, Any]:
        lease = datetime.now(UTC) + timedelta(minutes=lease_minutes)
        async with self.db.transaction() as conn:
            cur = await conn.execute("""UPDATE healthmind.ai_tasks
              SET deadline_at=%s,context_manifest=jsonb_set(context_manifest,'{hmc_lease_until}',to_jsonb(%s::text)),
                  lock_version=lock_version+1,updated_at=now()
              WHERE task_id=%s AND status='running' AND context_manifest->>'hmc_mcp_session'='true'
              RETURNING task_id,trace_id,status""", (lease, lease.isoformat(), task_id))
            task = await cur.fetchone()
            if not task:
                raise RuntimeError("调试任务不存在或已经结束")
            cur = await conn.execute("""UPDATE healthmind.ai_task_attempts
              SET started_at=now(),timeout_ms=3600000,
                  execution_metadata=jsonb_set(execution_metadata,'{hmc_lease_until}',to_jsonb(%s::text))
              WHERE task_id=%s AND status='running' RETURNING attempt_id""", (lease.isoformat(), task_id))
            attempt = await cur.fetchone()
            if not attempt:
                raise RuntimeError("调试 attempt 不再是 running")
        return {**dict(task), "attempt_id": attempt["attempt_id"], "lease_until": lease}

    async def close_mcp_session(self, task_id: str, automatic: bool = False) -> dict[str, Any]:
        code = "HMC_SESSION_EXPIRED" if automatic else "HMC_SESSION_CLOSED"
        async with self.db.transaction() as conn:
            cur = await conn.execute("""UPDATE healthmind.ai_task_attempts a
              SET status='cancelled',finished_at=now(),failure_category='cancelled',failure_code=%s,
                  failure_message='HealthMindControl MCP test session closed',
                  duration_ms=GREATEST(0,EXTRACT(EPOCH FROM (now()-started_at))*1000)::bigint
              FROM healthmind.ai_tasks t
              WHERE a.task_id=t.task_id AND t.task_id=%s AND t.status='running' AND a.status='running'
                AND t.context_manifest->>'hmc_mcp_session'='true' RETURNING a.attempt_id""", (code, task_id))
            attempt = await cur.fetchone()
            if not attempt:
                raise RuntimeError("调试任务不存在或已经结束")
            cur = await conn.execute("""UPDATE healthmind.ai_tasks SET status='cancelled',completed_at=now(),
                  failure_code=%s,failure_message='HealthMindControl MCP test session closed',
                  lock_version=lock_version+1,updated_at=now()
              WHERE task_id=%s AND status='running' RETURNING task_id,status,trace_id""", (code, task_id))
            task = await cur.fetchone()
        return {**dict(task), "attempt_id": attempt["attempt_id"]}

    async def close_expired_mcp_sessions(self) -> list[str]:
        rows = await self.db.fetch_all("""
            SELECT task_id FROM healthmind.ai_tasks
             WHERE status='running' AND context_manifest->>'hmc_mcp_session'='true'
               AND (context_manifest->>'hmc_lease_until')::timestamptz <= now()
             ORDER BY created_at LIMIT 50
        """)
        closed: list[str] = []
        for row in rows:
            try:
                await self.close_mcp_session(str(row["task_id"]), automatic=True)
                closed.append(str(row["task_id"]))
            except RuntimeError:
                continue
        return closed

    async def mcp_session_invocations(self, task_id: str) -> list[dict[str, Any]]:
        return await self.db.fetch_all("""
            SELECT i.invocation_id,d.tool_code,i.tool_call_id,i.authorized_scope,i.status,
                   i.started_at,i.completed_at,i.duration_ms,i.failure_code,i.failure_message,i.created_at
              FROM healthmind.ai_tool_invocations i
              JOIN healthmind.ai_tool_definitions d USING(tool_id)
             WHERE i.task_id=%s ORDER BY i.created_at
        """, (task_id,))

    async def release_fixture_outbox(self, schema_name: str, event_id: str) -> dict[str, Any]:
        if schema_name not in {"healthmind", "nutri"}:
            raise ValueError("schema 无效")
        async with self.db.transaction() as conn:
            if schema_name == "nutri":
                cur = await conn.execute("""UPDATE nutri.integration_outbox
                    SET next_attempt_at=now(),locked_at=NULL
                    WHERE event_id=%s AND status IN ('pending','failed') RETURNING *""", (event_id,))
            else:
                cur = await conn.execute("""UPDATE healthmind.integration_outbox
                    SET next_attempt_at=now()
                    WHERE event_id=%s AND status IN ('pending','failed') RETURNING *""", (event_id,))
            row = await cur.fetchone()
            if not row:
                raise RuntimeError("outbox 不存在或状态不可放行")
            return dict(row)
