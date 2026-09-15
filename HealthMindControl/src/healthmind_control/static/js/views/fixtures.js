import { esc, fmtTs, getJson, openDrawer, toast } from "../main.js";
import { startMutation } from "../flow.js";

const byId = (id) => document.getElementById(id);
let tables = [];
let currentDraft = null;
let invocationTimer = null;

const PRESETS = {
  hm_inbox: { table: "healthmind.integration_inbox", values: { status: "processed" } },
  task_queued: { table: "healthmind.ai_tasks", values: { status: "queued" } },
  task_running: { table: "healthmind.ai_tasks", values: { status: "running" } },
  task_failed: { table: "healthmind.ai_tasks", values: { status: "failed", failure_code: "HMC_TEST_FAILURE" } },
  attempt_running: { table: "healthmind.ai_task_attempts", values: { status: "running", timeout_ms: "3600000" } },
  attempt_succeeded: { table: "healthmind.ai_task_attempts", values: { status: "succeeded" } },
  attempt_failed: { table: "healthmind.ai_task_attempts", values: { status: "failed", failure_category: "permanent", failure_code: "HMC_TEST_FAILURE" } },
  result: { table: "healthmind.ai_task_results", values: {} },
  hm_outbox: { table: "healthmind.integration_outbox", values: { status: "pending" } },
  nutri_inbox: { table: "nutri.integration_inbox", values: { status: "processing" } },
  nutri_outbox: { table: "nutri.integration_outbox", values: { status: "pending" } },
};

function queryDefaults() {
  const query = new URLSearchParams(location.search);
  const source = query.get("source") || "";
  byId("fx-mcp-source").value = source;
  byId("fx-source").value = source;
}

function sessionCard(result) {
  if (invocationTimer) clearInterval(invocationTimer);
  const inputs = { task_id: result.task_id, attempt_id: result.attempt_id, trace_id: result.trace_id };
  const raw = JSON.stringify(inputs, null, 2);
  byId("fx-mcp-session").innerHTML = '<div class="session-card" data-task="' + esc(result.task_id) + '">'
    + '<div class="row spread"><div><span class="badge b-ok">MCP 可读取</span> <b>测试 ID 已准备</b></div>'
    + '<span class="small muted">有效至 ' + esc(fmtTs(result.lease_until)) + '</span></div>'
    + '<pre class="code">' + esc(raw) + '</pre>'
    + '<div class="row"><button class="btn primary" data-copy=\'' + esc(raw) + '\'>复制 Dify 输入 JSON</button>'
    + '<button class="btn" id="fx-renew" type="button">续期</button><button class="btn danger" id="fx-close" type="button">结束测试</button>'
    + '<a class="btn ghost" href="/ui/trace?q=' + esc(result.task_id) + '">查看链路</a></div>'
    + '<div id="fx-life-flow" class="flow-box"></div><h3 style="margin-top:14px">MCP 工具调用流</h3>'
    + '<div id="fx-invocations" class="muted">等待 Dify 调用…</div></div>';
  byId("fx-renew").addEventListener("click", () => lifecycle(result.task_id, "renew"));
  byId("fx-close").addEventListener("click", () => lifecycle(result.task_id, "close"));
  pollInvocations(result.task_id);
  invocationTimer = setInterval(() => pollInvocations(result.task_id), 3000);
}

async function pollInvocations(taskId) {
  try {
    const data = await getJson("/api/fixtures/mcp-session/" + encodeURIComponent(taskId) + "/invocations");
    const rows = data.invocations || [];
    byId("fx-invocations").innerHTML = rows.length ? '<div class="tbl-wrap"><table class="tbl"><thead><tr>'
      + '<th>时间</th><th>工具</th><th>Scope</th><th>状态</th><th>耗时</th><th>错误</th></tr></thead><tbody>'
      + rows.map((r) => '<tr><td>' + esc(fmtTs(r.created_at)) + '</td><td class="mono">' + esc(r.tool_code)
        + '</td><td class="mono small">' + esc(r.authorized_scope || "-") + '</td><td><span class="badge">' + esc(r.status)
        + '</span></td><td>' + esc(r.duration_ms == null ? "-" : r.duration_ms + " ms") + '</td><td>'
        + esc(r.failure_code || "-") + '</td></tr>').join("") + '</tbody></table></div>'
      : '<span class="muted">等待 Dify 调用…</span>';
  } catch (e) {
    if (byId("fx-invocations")) byId("fx-invocations").textContent = "读取调用记录失败：" + e.message;
  }
}

function lifecycle(taskId, action) {
  startMutation(byId("fx-life-flow"), {
    previewUrl: "/api/fixtures/mcp-session/" + taskId + "/" + action + "/preview",
    executeUrl: "/api/fixtures/mcp-session/" + taskId + "/" + action,
    body: () => ({ task_id: taskId, reason: action === "renew" ? "继续 MCP 手动测试" : "结束 MCP 手动测试" }),
    onDone: (result) => {
      if (action === "close") {
        clearInterval(invocationTimer); invocationTimer = null;
        toast("测试任务已结束，记录保留", "ok");
      } else sessionCard(result);
    },
  });
}

function createMcpSession() {
  const source = byId("fx-mcp-source").value.trim();
  if (!source) return toast("请输入源任务 ID", "warn");
  startMutation(byId("fx-mcp-flow"), {
    previewUrl: "/api/fixtures/mcp-session/preview",
    executeUrl: "/api/fixtures/mcp-session/execute",
    body: () => ({ source_task_id: source, inherit_trace_id: byId("fx-mcp-trace").checked,
      reason: byId("fx-mcp-reason").value }),
    onDone: sessionCard,
  });
}

function fieldValue(mapping) {
  if (mapping.mode === "manual") {
    if (mapping.value === null || mapping.value === undefined) return "";
    return typeof mapping.value === "object" ? JSON.stringify(mapping.value) : String(mapping.value);
  }
  if (mapping.mode === "generate") return mapping.generator || "uuid";
  return mapping.source_field || "";
}

function renderFields(draft) {
  currentDraft = draft;
  const constraints = draft.table.constraints || [];
  byId("fx-table-note").textContent = "主键：" + draft.table.primary_key.join(", ")
    + "；约束：" + constraints.map((c) => c.conname).join(", ");
  byId("fx-fields").innerHTML = '<div class="tbl-wrap"><table class="tbl fixture-map"><thead><tr>'
    + '<th>字段</th><th>类型/约束</th><th>取值方式</th><th>来源路径 / 生成器 / 手动值</th></tr></thead><tbody>'
    + draft.table.columns.map((column) => {
      const m = draft.mappings[column.column_name] || { mode: "omit" };
      const opts = ["omit", "inherit", "related", "generate", "manual"].map((mode) =>
        '<option value="' + mode + '"' + (m.mode === mode ? " selected" : "") + '>'
        + ({ omit: "省略/数据库默认", inherit: "继承源字段", related: "关联字段", generate: "自动生成", manual: "手动输入" })[mode]
        + '</option>').join("");
      const note = column.nullable ? "可空" : "必填";
      return '<tr data-column="' + esc(column.column_name) + '" data-type="' + esc(column.udt_name) + '"><td><b class="mono">'
        + esc(column.column_name) + '</b></td><td class="small muted">' + esc(column.udt_name) + ' · ' + note
        + (column.column_default ? ' · 默认值' : '') + '</td><td><select class="map-mode">' + opts
        + '</select></td><td><textarea class="map-value" rows="1">' + esc(fieldValue(m)) + '</textarea></td></tr>';
    }).join("") + '</tbody></table></div>';
  byId("fx-preview").disabled = false;
}

function applyPresetValues(preset) {
  if (!preset) return;
  Object.entries(preset.values || {}).forEach(([name, value]) => {
    const row = document.querySelector('#fx-fields tr[data-column="' + CSS.escape(name) + '"]');
    if (!row) return;
    row.querySelector(".map-mode").value = "manual";
    row.querySelector(".map-value").value = String(value);
  });
  const terminal = ["task_failed", "attempt_succeeded", "attempt_failed"].includes(byId("fx-preset").value);
  if (terminal) {
    ["completed_at", "finished_at"].forEach((name) => {
      const row = document.querySelector('#fx-fields tr[data-column="' + name + '"]');
      if (!row) return;
      row.querySelector(".map-mode").value = "generate";
      row.querySelector(".map-value").value = "now";
    });
  }
  if (["task_running", "attempt_running"].includes(byId("fx-preset").value)) {
    const row = document.querySelector('#fx-fields tr[data-column="started_at"]');
    if (row) { row.querySelector(".map-mode").value = "generate"; row.querySelector(".map-value").value = "now"; }
  }
}

async function loadDraft() {
  const table = byId("fx-table").value;
  const source = byId("fx-source").value.trim();
  const url = "/api/fixtures/draft?table_name=" + encodeURIComponent(table)
    + (source ? "&source_identifier=" + encodeURIComponent(source) : "");
  try {
    renderFields(await getJson(url));
    applyPresetValues(PRESETS[byId("fx-preset").value]);
  }
  catch (e) { toast("加载字段失败：" + e.message, "err"); }
}

function mappingsFromForm() {
  const mappings = {};
  document.querySelectorAll("#fx-fields tr[data-column]").forEach((row) => {
    const name = row.dataset.column;
    const mode = row.querySelector(".map-mode").value;
    const text = row.querySelector(".map-value").value.trim();
    const mapping = { mode };
    if (mode === "inherit" || mode === "related") mapping.source_field = text || ("flat." + name);
    if (mode === "generate") mapping.generator = text || "uuid";
    if (mode === "manual") {
      if (!text) mapping.value = null;
      else if (["json", "jsonb"].includes(row.dataset.type)) {
        try { mapping.value = JSON.parse(text); } catch { throw new Error(name + " 不是合法 JSON"); }
      } else mapping.value = text;
    }
    mappings[name] = mapping;
  });
  return mappings;
}

function previewFixture() {
  let target;
  try { target = JSON.parse(byId("fx-target").value || "{}"); }
  catch { return toast("更新目标主键不是合法 JSON", "err"); }
  startMutation(byId("fx-flow"), {
    previewUrl: "/api/fixtures/preview", executeUrl: "/api/fixtures/execute",
    body: () => ({ operation: byId("fx-operation").value, table_name: byId("fx-table").value,
      source_identifier: byId("fx-source").value.trim() || null, target,
      mappings: mappingsFromForm(), reason: byId("fx-reason").value }),
    onDone: (result) => openDrawer("数据构造结果", result),
  });
}

function releaseOutbox() {
  startMutation(byId("fx-out-flow"), {
    previewUrl: "/api/fixtures/outbox/release/preview", executeUrl: "/api/fixtures/outbox/release",
    body: () => ({ schema_name: byId("fx-out-schema").value, event_id: byId("fx-out-event").value.trim(),
      reason: byId("fx-out-reason").value }),
    onDone: (result) => openDrawer("Outbox 已放行", result),
  });
}

async function init() {
  queryDefaults();
  tables = await getJson("/api/fixtures/tables");
  byId("fx-table").innerHTML = tables.map((t) => '<option value="' + esc(t.table_name) + '">' + esc(t.table_name) + '</option>').join("");
  byId("fx-mcp-create").addEventListener("click", createMcpSession);
  byId("fx-load").addEventListener("click", loadDraft);
  byId("fx-preview").addEventListener("click", previewFixture);
  byId("fx-out-release").addEventListener("click", releaseOutbox);
  byId("fx-operation").addEventListener("change", () => {
    byId("fx-target").disabled = byId("fx-operation").value !== "update";
  });
  byId("fx-preset").addEventListener("change", async () => {
    const preset = PRESETS[byId("fx-preset").value];
    if (preset) byId("fx-table").value = preset.table;
    await loadDraft();
  });
  if (new URLSearchParams(location.search).get("preset") === "mcp") byId("fx-mcp-source").focus();
  await loadDraft();
}

init().catch((e) => toast("数据构造器加载失败：" + e.message, "err"));
