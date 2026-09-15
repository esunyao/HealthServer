import { esc, fmtTs, getJson, postJson, toast, openDrawer } from "../main.js";
import { startMutation } from "../flow.js";

let runs = [], current = null;
const $ = (id) => document.getElementById(id);

async function loadRuns(selectId) {
  runs = await getJson("/api/debug/runs");
  $("d-runs").innerHTML = '<option value="">选择运行…</option>' + runs.map((r) =>
    '<option value="' + esc(r.run_id) + '">' + esc(r.name) + " · " + esc(r.mode) + "</option>").join("");
  if (selectId) $("d-runs").value = selectId;
  await selectRun();
}

async function selectRun() {
  const id = $("d-runs").value;
  if (!id) { current = null; $("d-run-meta").textContent = "尚未选择运行"; return; }
  current = await getJson("/api/debug/runs/" + id);
  $("d-run-meta").innerHTML = '<span class="badge b-ok">' + esc(current.status) + '</span> '
    + '<span class="mono">' + esc(current.run_id) + "</span><pre class=\"code\">" + esc(JSON.stringify(current.context, null, 2)) + "</pre>";
  await observe();
}

async function observe() {
  if (!current) return toast("请先创建或选择调试运行", "warn");
  const data = await getJson("/api/debug/runs/" + current.run_id + "/observe");
  const tables = data.tables || {};
  $("d-evidence").innerHTML = Object.entries(tables).map(([name, rows]) =>
    '<details open><summary><b>' + esc(name) + '</b> <span class="badge">' + rows.length + '</span></summary>'
      + (rows.length ? '<pre class="code">' + esc(JSON.stringify(rows, null, 2)) + '</pre>' : '<p class="muted">无匹配记录</p>') + '</details>').join("");
}

function previewStage(card) {
  if (!current) return toast("请先创建或选择调试运行", "warn");
  const step = card.dataset.step;
  let params = {};
  const paramsEl = card.querySelector(".stage-params");
  if (paramsEl && paramsEl.value.trim()) {
    try { params = JSON.parse(paramsEl.value); } catch { return toast("步骤参数不是合法 JSON", "err"); }
  }
  const recordId = card.querySelector(".stage-id").value.trim() || null;
  const reason = "debug run " + current.run_id + " step " + step;
  startMutation(card.querySelector(".stage-flow"), {
    previewUrl: "/api/debug/runs/" + current.run_id + "/steps/" + step + "/preview",
    executeUrl: "/api/debug/runs/" + current.run_id + "/steps/" + step + "/execute",
    body: () => ({ record_id: recordId, params, reason }),
    onDone: async (result) => { await loadRuns(current.run_id); openDrawer("步骤结果", result); },
  });
}

async function searchUsers() {
  const q = $("d-user-q").value.trim(); if (q.length < 2) return toast("至少输入 2 个字符", "warn");
  const users = await getJson("/api/debug/users?q=" + encodeURIComponent(q));
  $("d-users").innerHTML = users.map((u) => '<button class="user-hit" data-user="' + esc(u.user_id) + '"><b>'
    + esc(u.username) + '</b><span>' + esc(u.email || u.user_id) + '</span></button>').join("") || '<p class="muted">未找到</p>';
  $("d-users").querySelectorAll(".user-hit").forEach((b) => b.addEventListener("click", () => {
    $("d-new-context").value = JSON.stringify({ user_id: b.dataset.user }, null, 2); $("d-new-dialog").showModal();
  }));
}

function previewSql() {
  startMutation($("d-sql-flow"), {
    previewUrl: "/api/expert/sql/preview", executeUrl: "/api/expert/sql/execute", title: "专家 SQL",
    body: () => ({ sql: $("d-sql").value, database: "primary", reason: $("d-sql-reason").value }),
    onDone: (result) => openDrawer("SQL 结果", result),
  });
}

$("d-runs").addEventListener("change", selectRun); $("d-observe").addEventListener("click", observe);
$("d-user-search").addEventListener("click", searchUsers);
document.querySelectorAll(".stage-preview").forEach((b) => b.addEventListener("click", () => previewStage(b.closest(".stage"))));
$("d-new").addEventListener("click", () => $("d-new-dialog").showModal());
$("d-new-cancel").addEventListener("click", () => $("d-new-dialog").close());
$("d-new-save").addEventListener("click", async () => {
  let context; try { context = JSON.parse($("d-new-context").value || "{}"); } catch { return toast("上下文 JSON 无效", "err"); }
  const run = await postJson("/api/debug/runs", { name: $("d-new-name").value, mode: $("d-new-mode").value, context });
  $("d-new-dialog").close(); await loadRuns(run.run_id); toast("调试运行已创建", "ok");
});
if ($("d-sql-preview")) $("d-sql-preview").addEventListener("click", previewSql);
loadRuns().catch((e) => toast("实验台加载失败：" + e.message, "err"));
