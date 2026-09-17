// Dify 版本管理视图
import { esc, fmtTs, getJson, postJson, toast, $, openDrawer } from "../main.js";
import { renderJsonTreeEl } from "../json-tree.js";
import { startMutation } from "../flow.js";

let toolsDefs = [];
const DEFAULT_TOOLS = ["nutrimemo.capture_context.get", "orion.nutrition_context.get"];

// ---------------- 工具定义复选框 ----------------
async function loadToolDefs(selected) {
  try { toolsDefs = await getJson("/api/dify/tool-definitions"); } catch (e) { toast("工具定义加载失败：" + e.message, "warn"); }
  const box = document.getElementById("w-tools");
  box.innerHTML = "";
  toolsDefs.forEach(function (t) {
    const label = document.createElement("label");
    label.className = "check-line";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = t.tool_code;
    cb.checked = (selected || DEFAULT_TOOLS).includes(t.tool_code);
    cb.style.margin = "0";
    label.appendChild(cb);
    label.appendChild(document.createTextNode(t.tool_code + "（" + t.owner_service + "）"));
    box.appendChild(label);
  });
}

function selectedTools() {
  return Array.from(document.querySelectorAll("#w-tools input:checked")).map(function (c) { return c.value; });
}

function readSchemas() {
  const input = JSON.parse(document.getElementById("w-input").value);
  const output = JSON.parse(document.getElementById("w-output").value);
  return { input: input, output: output };
}

function createBody() {
  const schemas = readSchemas();
  return {
    operation: "create",
    release_version: document.getElementById("w-version").value.trim(),
    workspace_id: document.getElementById("w-workspace").value.trim(),
    app_id: document.getElementById("w-appid").value.trim(),
    workflow_id: document.getElementById("w-workflow").value.trim(),
    workflow_version: document.getElementById("w-wfversion").value.trim(),
    input_schema: schemas.input,
    output_schema: schemas.output,
    tool_codes: selectedTools(),
    reason: document.getElementById("w-reason").value.trim(),
  };
}

function previewCreate() {
  startMutation(document.getElementById("w-preview-box"), {
    previewUrl: "/api/releases/preview",
    executeUrl: "/api/releases/execute",
    body: createBody,
    onDone: function () { loadReleases(); },
  });
}

// ---------------- 列表 ----------------
function transitionOp(operation, releaseId) {
  const reason = window.prompt("操作原因（写入 DB 审计与 JSONL，≥3 字符）");
  if (!reason || reason.trim().length < 3) { toast("原因过短", "warn"); return; }
  const body = { operation: operation, release_id: releaseId, reason: reason.trim() };
  const host = document.getElementById("op-flow-host");
  host.innerHTML = "<div class=\"card warn-line\" style=\"padding:12px 14px\"><h3 style=\"margin:0 0 8px;font-size:13.5px\">RELEASE " + esc(operation.toUpperCase()) + " · " + esc(String(releaseId).slice(0, 13)) + "…</h3><div id=\"op-flow-inner\"></div></div>";
  startMutation(document.getElementById("op-flow-inner"), {
    previewUrl: "/api/releases/preview",
    executeUrl: "/api/releases/execute",
    body: function () { return body; },
    onDone: function () { loadReleases(); },
  });
}

function renderList(list) {
  const box = document.getElementById("rel-list");
  if (!list.length) { box.innerHTML = '<div class="muted">尚无版本（先用上方向导登记 candidate）</div>'; return; }
  box.innerHTML = '<div class="tbl-wrap"><table class="tbl"><thead><tr>'
    + "<th>版本</th><th>状态</th><th>app / workflow</th><th>workflow ver</th><th>绑定工具</th><th>创建/提升</th><th>操作</th></tr></thead><tbody>"
    + list.map(function (r) {
      const tools = (r.tools || []).map(function (t) {
        return '<span class="badge b-accent" title="scope: ' + esc(t.scope || "") + '">' + esc(t.tool_code) + "</span>";
      }).join("");
      const stCls = r.status === "production" ? "b-ok" : r.status === "retired" ? "b-mut" : "b-warn";
      const acts = [];
      acts.push('<button class="btn sm" data-drawer-url="/api/releases/' + r.release_id + '" data-drawer-title="版本详情">详情</button>');
      acts.push('<button class="btn sm" data-drawer-url="/api/releases/' + r.release_id + '/audits" data-drawer-title="版本审计">审计</button>');
      if (r.status === "candidate") {
        acts.push('<button class="btn sm" data-bind="' + r.release_id + '">绑定工具</button>');
        acts.push('<button class="btn sm primary" data-op="promote" data-id="' + r.release_id + '">提升 production</button>');
        acts.push('<button class="btn sm danger" data-op="retire" data-id="' + r.release_id + '">退役</button>');
      } else if (r.status === "production") {
        acts.push('<button class="btn sm danger" data-op="retire" data-id="' + r.release_id + '">退役</button>');
      } else {
        acts.push('<button class="btn sm" data-op="rollback" data-id="' + r.release_id + '">回滚至此</button>');
      }
      return "<tr><td><div class=\"mono-cell ellip\" style=\"max-width:170px\" title=\"" + esc(r.release_id) + '">' + esc(r.release_version) + "</div>"
        + '<div class="small muted">' + esc(String(r.release_id).slice(0, 13)) + "…</div></td>"
        + '<td><span class="badge ' + stCls + '">' + esc(r.status) + "</span></td>"
        + '<td class="mono-cell small">' + esc(String(r.dify_app_id || "").slice(0, 12)) + " / " + esc(String(r.dify_workflow_id || "").slice(0, 12)) + "</td>"
        + '<td class="small muted">' + esc(r.dify_workflow_version || "-") + "</td>"
        + "<td><div class=\"row\" style=\"gap:4px\">" + (tools || '<span class="muted small">无</span>') + "</div></td>"
        + '<td class="time-cell small">' + fmtTs(r.created_at) + (r.promoted_at ? "<br>↑ " + fmtTs(r.promoted_at) : "") + "</td>"
        + '<td><div class="row-actions">' + acts.join("") + "</div></td></tr>";
    }).join("") + "</tbody></table></div>";

  box.querySelectorAll("[data-op]").forEach(function (btn) {
    btn.addEventListener("click", function () { transitionOp(btn.dataset.op, btn.dataset.id); });
  });
  box.querySelectorAll("[data-bind]").forEach(function (btn) {
    btn.addEventListener("click", function () { openBindTools(btn.dataset.bind); });
  });
}

async function loadReleases() {
  try { renderList(await getJson("/api/releases")); }
  catch (e) { toast("版本列表加载失败：" + e.message, "err"); }
}

// ---------------- 绑定工具（抽屉内编辑 + 预览流） ----------------
async function openBindTools(releaseId) {
  let detail, defs;
  try { [detail, defs] = await Promise.all([getJson("/api/releases/" + releaseId), getJson("/api/dify/tool-definitions")]); }
  catch (e) { toast(e.message, "err"); return; }
  const current = (detail.tools || []).map(function (t) { return t.tool_code; });
  const wrap = document.createElement("div");
  wrap.innerHTML = '<div class="small muted" style="margin-bottom:8px">仅 candidate 可修改；scope 取工具定义 auth_scope</div>';
  defs.forEach(function (t) {
    const label = document.createElement("label");
    label.className = "check-line";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = t.tool_code;
    cb.checked = current.includes(t.tool_code);
    label.appendChild(cb);
    label.appendChild(document.createTextNode(t.tool_code + "（" + t.owner_service + "）"));
    wrap.appendChild(label);
  });
  const reasonBox = document.createElement("input");
  reasonBox.type = "text";
  reasonBox.placeholder = "操作原因（≥3 字符）";
  reasonBox.style.marginTop = "8px";
  wrap.appendChild(reasonBox);
  const resultBox = document.createElement("div");
  resultBox.style.marginTop = "8px";
  wrap.appendChild(resultBox);
  const go = document.createElement("button");
  go.className = "btn danger";
  go.textContent = "保存绑定（预览）";
  go.style.marginTop = "8px";
  go.addEventListener("click", function () {
    const bindings = Array.from(wrap.querySelectorAll("input[type=checkbox]:checked")).map(function (c) {
      return { tool_code: c.value, required: true, max_calls: 1, timeout_ms: 10000 };
    });
    startMutation(resultBox, {
      previewUrl: "/api/releases/" + releaseId + "/tools/preview",
      executeUrl: "/api/releases/" + releaseId + "/tools/execute",
      body: function () { return { release_id: releaseId, bindings: bindings, reason: reasonBox.value.trim() }; },
      onDone: function () { loadReleases(); closeAndReload(); },
    });
  });
  wrap.appendChild(go);
  openDrawer("绑定工具 · " + String(releaseId).slice(0, 12) + "…", wrap);
}

// ---------------- 向导辅助 ----------------
function fillFields(f) {
  if (f.workspace_id) document.getElementById("w-workspace").value = f.workspace_id;
  if (f.app_id) document.getElementById("w-appid").value = f.app_id;
  if (f.workflow_id) document.getElementById("w-workflow").value = f.workflow_id;
  if (f.workflow_version) document.getElementById("w-wfversion").value = f.workflow_version;
  if (f.release_version && !document.getElementById("w-version").value) document.getElementById("w-version").value = f.release_version;
  if (f.input_schema && typeof f.input_schema === "object") {
    document.getElementById("w-input").value = JSON.stringify(f.input_schema, null, 2);
    toast("已按 DSL user_input_form 生成 input schema 草案，请核对 required/格式", "warn");
  }
}

function parsePublish() {
  const text = document.getElementById("w-publish").value.trim();
  if (!text) { toast("先粘贴 publish JSON 或 DSL", "warn"); return; }
  postJson("/api/dify/analyze", { text: text }).then(function (proposal) {
    if (!proposal.fields || !Object.keys(proposal.fields).length) {
      openDrawer("无法识别结构", renderJsonTreeEl(proposal));
      return;
    }
    fillFields(proposal.fields);
    toast("已解析：" + (proposal.hints || []).join("；"), "ok");
  }).catch(function (e) { toast("解析失败：" + e.message, "err"); });
}

function renderDifyctlStatus(res) {
  const host = document.getElementById("w-cli-status");
  if (!res.authenticated) {
    host.className = "small warn-line";
    host.textContent = res.login_hint || "difyctl 尚未登录";
    return;
  }
  const account = res.account || {};
  const server = (res.version && res.version.server) || {};
  const warning = res.compatibility_warning ? "；兼容性提示：" + res.compatibility_warning : "";
  host.className = "small " + (warning ? "warn-line" : "muted");
  host.textContent = "difyctl 已登录：" + (account.email || account.name || account.id || "当前账户")
    + (server.version ? "；Dify " + server.version : "") + warning;
}

function renderDifyctlDetail(res) {
  const detail = document.getElementById("w-cli-detail");
  detail.innerHTML = "";
  detail.appendChild(renderJsonTreeEl({
    input_schema: res.resolved && res.resolved.dify_input_schema,
    dsl: res.dsl,
    errors: res.errors,
  }));
}

function populateApps(apps, selected) {
  const select = document.getElementById("w-app");
  const workflowApps = (apps || []).filter(function (app) { return app.mode === "workflow"; });
  select.innerHTML = "";
  if (!workflowApps.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "没有可用的 workflow 应用";
    select.appendChild(option);
    return "";
  }
  workflowApps.forEach(function (app) {
    const option = document.createElement("option");
    option.value = app.id;
    option.textContent = app.name + " · " + app.id;
    select.appendChild(option);
  });
  select.value = workflowApps.some(function (app) { return app.id === selected; }) ? selected : workflowApps[0].id;
  return select.value;
}

async function loadDifyctlApps(reloadSelected) {
  const select = document.getElementById("w-app");
  const selected = select.value;
  try {
    const res = await getJson("/api/dify/discover");
    renderDifyctlStatus(res);
    if (res.resolved) fillFields(res.resolved);
    const appId = populateApps(res.apps, selected);
    if (res.authenticated && appId && reloadSelected !== false) await loadDifyctlApp(appId);
    else if (Object.keys(res.errors || {}).length) renderDifyctlDetail(res);
  } catch (e) {
    document.getElementById("w-cli-status").textContent = "difyctl 探测失败：" + e.message;
    toast("difyctl 探测失败：" + e.message, "err");
  }
}

async function loadDifyctlApp(appId) {
  if (!appId) return;
  try {
    const res = await getJson("/api/dify/discover?app_id=" + encodeURIComponent(appId) + "&with_dsl=true");
    renderDifyctlStatus(res);
    if (res.resolved) {
      // Dify 的运行输入 Schema 与 HealthMind 的 Kafka 事件契约不同，只展示，不覆盖发布 input_schema。
      fillFields({ workspace_id: res.resolved.workspace_id, app_id: res.resolved.app_id });
    }
    renderDifyctlDetail(res);
    if (Object.keys(res.errors || {}).length) toast("部分 difyctl 信息读取失败，请展开查看", "warn");
  } catch (e) { toast("应用读取失败：" + e.message, "err"); }
}

// ---------------- 审计查询 ----------------
async function loadAudits() {
  const rid = document.getElementById("audit-rel").value.trim();
  const url = rid ? "/api/releases/" + encodeURIComponent(rid) + "/audits" : "/api/audits/releases";
  try {
    const rows = await getJson(url);
    const box = document.getElementById("audit-box");
    if (!rows.length) { box.innerHTML = '<div class="muted">无审计记录</div>'; return; }
    box.innerHTML = '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>时间</th><th>操作</th><th>版本</th><th>状态迁移</th><th>操作者</th><th>原因</th></tr></thead><tbody>'
      + rows.map(function (a) {
        return "<tr>"
          + '<td class="time-cell">' + fmtTs(a.occurred_at) + "</td>"
          + '<td><span class="badge ' + (a.action === "promoted" || a.action === "rolled_back" ? "b-ok" : a.action === "retired" ? "b-mut" : "b-info") + '">' + esc(a.action) + "</span></td>"
          + '<td class="mono-cell small">' + esc(String(a.release_id || "").slice(0, 13)) + "… " + esc(a.release_version || "") + "</td>"
          + '<td class="small">' + esc(a.from_status || "-") + " → " + esc(a.to_status) + "</td>"
          + '<td>' + esc(a.actor_id || "-") + "</td>"
          + '<td class="small muted ellip" style="max-width:260px" title="' + esc(a.reason || "") + '">' + esc(a.reason || "") + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  } catch (e) { toast("审计查询失败：" + e.message, "err"); }
}

function init() {
  document.getElementById("w-parse").addEventListener("click", parsePublish);
  document.getElementById("w-dsl").addEventListener("click", function () { loadDifyctlApps(true); });
  document.getElementById("w-app").addEventListener("change", function (event) { loadDifyctlApp(event.target.value); });
  document.getElementById("w-preview").addEventListener("click", previewCreate);
  document.getElementById("rel-reload").addEventListener("click", loadReleases);
  document.getElementById("audit-go").addEventListener("click", loadAudits);
  loadToolDefs(DEFAULT_TOOLS);
  loadReleases();
  loadDifyctlApps(true);
}
init();

// 供抽屉绑定执行成功后关闭
function closeAndReload() {
  const btn = document.querySelector("#drawer-close");
  if (btn) btn.click();
}
