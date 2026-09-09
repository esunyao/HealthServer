// 链路视图：按阶段时间线渲染 /api/traces/{id} 结果
import { esc, fmtTs, getJson, toast, $ } from "../main.js";

const KIND_ID = {
  nutri_meal_capture_sessions: "capture_session_id",
  nutri_integration_outbox: "event_id",
  healthmind_integration_inbox: "event_id",
  healthmind_ai_tasks: "task_id",
  healthmind_ai_task_attempts: "attempt_id",
  healthmind_ai_tool_invocations: "invocation_id",
  healthmind_ai_task_results: "result_id",
  healthmind_integration_outbox: "event_id",
  nutri_integration_inbox: "event_id",
  nutri_meal_records: "meal_id",
};
const TIME_KEYS = ["occurred_at", "received_at", "created_at", "started_at", "finished_at", "completed_at", "published_at", "processed_at", "updated_at"];
const STATUS_KEYS = ["status", "task_status", "capture_status", "analysis_status", "attempt_status", "invocation_status", "event_status"];

function pick(row, keys) {
  for (const k of keys) { if (row[k] !== undefined && row[k] !== null) return row[k]; }
  return null;
}

function stageClass(row) {
  const st = String(pick(row, STATUS_KEYS) || "").toLowerCase();
  if (["failed", "timed_out", "expired", "denied", "cancelled", "error"].some((w) => st.includes(w))) return "s-err";
  if (["succeeded", "processed", "published", "completed"].includes(st)) return "s-ok";
  if (["running", "pending", "queued", "processing", "publishing", "analysing"].includes(st)) return "s-info";
  return "s-mut";
}

function statusBadge(row) {
  const st = pick(row, STATUS_KEYS);
  if (st == null) return "";
  const cls = (["failed", "timed_out", "expired", "cancelled", "denied", "error"].includes(String(st).toLowerCase())) ? "b-err"
    : (["succeeded", "processed", "published", "completed"].includes(String(st).toLowerCase())) ? "b-ok"
    : (["running", "pending", "queued", "processing", "publishing", "analysing"].includes(String(st).toLowerCase())) ? "b-warn" : "b-info";
  return '<span class="badge ' + cls + '">' + esc(st) + "</span>";
}

function rowCell(row, kind) {
  const id = pick(row, [KIND_ID[kind]]);
  const time = pick(row, TIME_KEYS);
  const meta = [];
  if (row.failure_code) meta.push('<span class="badge b-err">' + esc(row.failure_code) + "</span>");
  if (row.attempt_no != null) meta.push("尝试#" + row.attempt_no);
  if (row.event_type) meta.push('<span class="badge">' + esc(row.event_type) + "</span>");
  if (row.task_type_code) meta.push(esc(row.task_type_code));
  if (row.aggregate_type && row.aggregate_id) meta.push(esc(row.aggregate_type) + ":" + esc(String(row.aggregate_id).slice(0, 16)));
  return '<div class="tl-meta">'
    + '<span class="mono-cell ellip" style="max-width:230px" title="' + esc(id) + '">' + esc(String(id).slice(0, 26)) + "</span>"
    + (time ? '<span class="tl-time">' + fmtTs(time) + "</span>" : "")
    + statusBadge(row) + meta.join("")
    + '<button class="btn sm ghost" data-drawer-url="/api/rows/' + kind + "/" + encodeURIComponent(id) + '" data-drawer-title="' + esc(kind) + '">详情</button>'
    + (kind === "healthmind_ai_tasks" ? '<a class="btn sm ghost" href="/ui/repair?q=' + encodeURIComponent(id) + '">修复</a>' : "")
    + "</div>";
}

function stageHtml(stage) {
  const rows = stage.rows || [];
  const cards = rows.map(function (r) {
    return '<div class="tl-node ' + stageClass(r) + '"><div class="tl-title"><b>' + esc(stage.label) + "</b>"
      + (stage.matched === "fuzzy" ? '<span class="badge b-warn" title="未直接命中关系，按内容模糊匹配">模糊命中</span>' : "")
      + rowCell(r, stage.kind) + "</div></div>";
  }).join("");
  return '<div class="timeline">' + cards + "</div>";
}

function render(result) {
  const box = document.getElementById("trace-result");
  if (!result || !result.stages || !result.stages.length) {
    box.innerHTML = '<div class="card"><div class="muted">未找到与该 ID 相关的任何记录（可尝试 meal_id / capture_session_id / 完整 UUID）</div></div>';
    return;
  }
  const summary = result.stages.map(function (s) {
    return '<span class="step-chip">' + esc(s.label) + " × " + (s.rows || []).length + "</span>";
  }).join("");
  box.innerHTML = '<div class="card"><h2 class="section">链路阶段 <span class="hint">查询: ' + esc(result.query) + "</span></h2>"
    + '<div class="row" style="margin-bottom:10px">' + summary + "</div>"
    + result.stages.map(function (s) { return stageHtml(s); }).join("")
    + "</div>";
}

async function run(q) {
  q = (q || "").trim();
  if (q.length < 3) { toast("请输入至少 3 个字符的 ID", "warn"); return; }
  const box = document.getElementById("trace-result");
  box.innerHTML = '<div class="card"><span class="spin"></span> 查询中…</div>';
  try { render(await getJson("/api/traces/" + encodeURIComponent(q))); }
  catch (e) { box.innerHTML = '<div class="card"><div class="muted">查询失败：' + esc(e.message) + "</div></div>"; }
}

function init() {
  const input = document.getElementById("trace-q");
  document.getElementById("trace-go").addEventListener("click", function () { run(input.value); });
  input.addEventListener("keydown", function (ev) { if (ev.key === "Enter") run(input.value); });
  const q = new URLSearchParams(location.search).get("q");
  if (q) { input.value = q; run(q); }
}
init();
