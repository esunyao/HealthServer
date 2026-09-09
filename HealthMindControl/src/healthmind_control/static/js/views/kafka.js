// Kafka 管理视图
import { esc, fmtTs, getJson, postJson, toast, $, openDrawer } from "../main.js";
import { renderJsonTreeEl } from "../json-tree.js";
import { startMutation } from "../flow.js";

let topicsMeta = { brokers: [], topics: [] };
let groupsData = [];
let timerM = null;

const BIZ = ["nutrition-capture-ready", "nutrition-analysis-completed", "nutrition-analysis-failed"];

function partHealth(topic, p) {
  const isOk = !!(p.healthy);
  return '<span class="badge ' + (isOk ? "b-ok" : "b-err") + '" title="leader=' + p.leader + " replicas=[" + (p.replicas || []).join(",")
    + "] isr=[" + (p.isrs || []).join(",") + "]" + (p.error ? " err:" + p.error : "") + '">p' + p.partition + (isOk ? "" : " ⚠") + "</span>";
}

function renderTopics() {
  const box = document.getElementById("k-topics");
  if (!topicsMeta.topics || !topicsMeta.topics.length) { box.innerHTML = '<div class="muted">无法获取 topic 列表</div>'; return; }
  const html = topicsMeta.topics.map(function (t) {
    const unhealthy = (t.partitions || []).filter(function (p) { return !p.healthy; });
    const parts = (t.partitions || []).map(function (p) {
      return '<div style="display:flex;justify-content:space-between;gap:6px;padding:2px 0">'
        + '<span class="badge ' + (p.healthy ? "b-ok" : "b-err") + '">p' + p.partition + "</span>"
        + '<span class="small muted mono">earliest ' + (p.earliest_offset ?? "-") + " · latest " + (p.latest_offset ?? "-") + "</span></div>";
    }).join("");
    return '<div style="padding:8px 0;border-bottom:1px solid var(--line-soft)">'
      + '<div class="row" style="gap:8px;flex-wrap:wrap"><b class="mono">' + esc(t.name) + "</b>"
      + (BIZ.includes(t.name) ? '<span class="badge b-accent">业务</span>' : "")
      + (unhealthy.length ? '<span class="badge b-err">异常分区 ' + unhealthy.length + "</span>" : '<span class="badge b-ok">健康</span>')
      + "</div><div>" + parts + "</div></div>";
  }).join("");
  box.innerHTML = '<div class="row small muted" style="margin-bottom:4px">brokers: ' + (topicsMeta.brokers || []).map(function (b) { return esc(b.host + ":" + b.port); }).join(", ") + "</div>" + html;
  fillSelects();
}

function fillSelects() {
  const topicSel = document.getElementById("m-topic");
  const current = topicSel.value;
  topicSel.innerHTML = topicsMeta.topics.map(function (t) { return '<option value="' + esc(t.name) + '">' + esc(t.name) + "</option>"; }).join("");
  if (current && topicsMeta.topics.some(function (t) { return t.name === current; })) topicSel.value = current;
  topicChanged();
  document.getElementById("topic-list").innerHTML = topicsMeta.topics.map(function (t) { return '<option value="' + esc(t.name) + '">'; }).join("");
}

function topicChanged() {
  const t = topicsMeta.topics.find(function (x) { return x.name === document.getElementById("m-topic").value; });
  const partSel = document.getElementById("m-partition");
  if (!t) { partSel.innerHTML = ""; return; }
  partSel.innerHTML = t.partitions.map(function (p) { return '<option value="' + p.partition + '">分区 ' + p.partition + "</option>"; }).join("");
  const p = t.partitions[0] || {};
  document.getElementById("m-range").textContent = "earliest=" + (p.earliest_offset ?? "-") + " latest=" + (p.latest_offset ?? "-");
}

function renderGroups() {
  const box = document.getElementById("k-groups");
  groupsData = groupsData.filter(function (g) { return !String(g.group_id).startsWith("healthmind-control-"); });
  if (!groupsData.length) { box.innerHTML = '<div class="muted">无消费组</div>'; return; }
  box.innerHTML = groupsData.map(function (g) {
    const rows = (g.offsets || []).map(function (o) {
      return '<tr><td class="mono-cell">' + esc(o.topic) + "</td><td class=\"num\">" + o.partition + "</td><td class=\"num\">" + o.offset + "</td><td class=\"num\">" + (o.high ?? "-") + "</td><td class=\"num\" style=\"color:" + ((o.lag || 0) > 0 ? "var(--warn)" : "var(--ok)") + '">' + (o.lag ?? "-") + "</td></tr>";
    }).join("");
    const members = (g.members || []).map(function (m) {
      const asg = (m.assignments || []).map(function (a) { return esc(a.topic) + "/" + a.partition; }).join(" ");
      return '<div class="small muted mono" title="' + esc(m.client_id || "") + " @ " + esc(m.host || "") + '">' + esc(String(m.member_id || "").slice(0, 22)) + (asg ? " · " + asg : "") + "</div>";
    }).join("");
    return '<details style="padding:8px 0;border-bottom:1px solid var(--line-soft)">'
      + '<summary class="row" style="gap:8px;cursor:pointer"><b class="mono">' + esc(g.group_id) + "</b>"
      + '<span class="badge">' + esc(g.state) + "</span>"
      + '<span class="badge ' + ((g.lag || 0) > 0 ? "b-warn" : "b-ok") + '">lag ' + (g.lag || 0) + "</span>"
      + '<span class="small muted">成员 ' + (g.members || []).length + "</span></summary>"
      + '<div style="margin:6px 0">' + (members || '<span class="muted small">无在线成员</span>') + "</div>"
      + '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>topic</th><th style="text-align:right">分区</th><th style="text-align:right">offset</th><th style="text-align:right">high</th><th style="text-align:right">lag</th></tr></thead><tbody>' + (rows || '<tr><td colspan="5" class="empty">无 offset</td></tr>') + "</tbody></table></div>"
      + "</details>";
  }).join("");
}

async function loadTopics(force) {
  try { topicsMeta = await getJson("/api/kafka/topics" + (force ? "?force=true" : "")); renderTopics(); }
  catch (e) { document.getElementById("k-topics").innerHTML = '<div class="muted">加载失败：' + esc(e.message) + "</div>"; }
}
async function loadGroups() {
  try { groupsData = await getJson("/api/kafka/groups"); renderGroups(); }
  catch (e) { document.getElementById("k-groups").innerHTML = '<div class="muted">加载失败：' + esc(e.message) + "</div>"; }
}

// ---------------- 消息查看 ----------------
function messageRow(m, idx) {
  const preview = typeof m.payload === "string" ? m.payload.slice(0, 90) : JSON.stringify(m.payload).slice(0, 90);
  return '<tr style="cursor:pointer" data-msg="' + idx + '">'
    + '<td class="time-cell">' + fmtTs(m.timestamp) + "</td>"
    + '<td class="num">' + m.offset + "</td>"
    + '<td class="mono-cell ellip" style="max-width:150px" title="' + esc(m.key || "") + '">' + esc(m.key || "-") + "</td>"
    + '<td class="num">' + Object.keys(m.headers || {}).length + "</td>"
    + '<td class="mono-cell ellip" style="max-width:300px">' + esc(preview) + "</td></tr>";
}

async function readMessages() {
  const params = { topic: document.getElementById("m-topic").value, partition: document.getElementById("m-partition").value };
  const start = document.getElementById("m-start").value;
  params.start = start;
  if (start === "offset") params.offset = document.getElementById("m-offset").value;
  if (start === "time") {
    const v = document.getElementById("m-time").value;
    if (!v) { toast("请选择时间", "warn"); return; }
    params.time_ms = String(new Date(v).getTime());
  }
  ["key", "event", "trace", "type", "contains"].forEach(function (k) {
    const v = document.getElementById("m-" + (k === "event" ? "event" : k === "type" ? "type" : k)).value;
    if (v) params[k === "event" ? "event_id" : k === "type" ? "event_type" : k] = v;
  });
  const qs = new URLSearchParams(params).toString();
  document.getElementById("m-status").textContent = "读取中…（扫描上限 5 万条）";
  try {
    const list = await getJson("/api/kafka/messages?" + qs);
    const truncated = list.some(function (m) { return m.truncated_by_scan; });
    const real = list.filter(function (m) { return !m.truncated_by_scan; });
    const body = document.getElementById("m-messages");
    if (!real.length) { body.innerHTML = '<div class="muted">该位置与过滤条件下没有消息' + (truncated ? "（已到扫描上限）" : "") + "</div>"; }
    else {
      body.innerHTML = '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>时间</th><th style="text-align:right">offset</th><th>key</th><th style="text-align:right">headers</th><th>payload 预览</th></tr></thead><tbody>'
        + real.map(function (m, i) { return messageRow(m, i); }).join("") + "</tbody></table></div>"
        + (truncated ? '<div class="small muted" style="margin-top:4px">已达扫描上限，还有更多匹配消息未显示</div>' : "");
      const rows = Array.from(body.querySelectorAll("tr[data-msg]"));
      rows.forEach(function (tr) {
        tr.addEventListener("click", function () {
          const msg = real[Number(tr.dataset.msg)];
          showMessage(msg);
        });
      });
    }
    document.getElementById("m-status").textContent = "返回 " + real.length + " 条" + (truncated ? "（截断）" : "");
  } catch (e) { toast("读取失败：" + e.message, "err"); document.getElementById("m-status").textContent = ""; }
}

function showMessage(m) {
  const meta = '<div class="msg-meta" style="margin-bottom:10px">'
    + "<div><b>Topic</b> " + esc(m.topic) + "</div>"
    + "<div><b>分区/Offset</b> " + m.partition + " / " + m.offset + "</div>"
    + "<div><b>时间</b> " + fmtTs(m.timestamp) + "</div>"
    + "<div><b>Key</b> " + esc(m.key || "-") + "</div>"
    + "</div>";
  const headers = Object.keys(m.headers || {}).length
    ? '<h3 style="font-size:13px;margin:8px 0 4px">Headers</h3><div class="msg-meta">' + Object.entries(m.headers).map(function (h) { return "<div><b>" + esc(h[0]) + "</b> " + esc(h[1]) + "</div>"; }).join("") + "</div>"
    : "";
  const payload = typeof m.payload === "string" ? m.payload : m.payload;
  const wrap = document.createElement("div");
  wrap.innerHTML = meta + headers;
  const title = document.createElement("div");
  title.innerHTML = '<h3 style="font-size:13px;margin:8px 0 4px">Payload</h3>';
  wrap.appendChild(title);
  wrap.appendChild(renderJsonTreeEl(payload));
  openDrawer("消息 " + m.topic + "/" + m.partition + "@" + m.offset, wrap);
}

// ---------------- 受控生产 ----------------
function bizTemplate() {
  const topic = document.getElementById("p-topic").value.trim();
  if (!BIZ.includes(topic)) { toast("仅三个业务 topic 提供模板", "warn"); return; }
  const now = new Date();
  const event = {
    event_id: crypto.randomUUID(),
    event_type: { "nutrition-capture-ready": "nutrition.capture.ready.v1", "nutrition-analysis-completed": "nutrition.analysis.completed.v1", "nutrition-analysis-failed": "nutrition.analysis.failed.v1" }[topic],
    occurred_at: now.toISOString(),
    producer: topic === "nutrition-capture-ready" ? "NutriMemo" : "HealthMind",
    trace_id: crypto.randomUUID(),
    subject_id: null,
    aggregate_type: "meal",
    aggregate_id: "",
    schema_version: "1.0",
    payload: {},
  };
  document.getElementById("p-payload").value = JSON.stringify(event, null, 2);
}

function headersObject() {
  const out = {};
  document.querySelectorAll("#p-headers .h-row").forEach(function (row) {
    const k = row.querySelector(".hk").value.trim();
    const v = row.querySelector(".hv").value;
    if (k) out[k] = v;
  });
  return out;
}
function addHeaderRow(k, v) {
  const box = document.getElementById("p-headers");
  const row = document.createElement("div");
  row.className = "row h-row";
  row.style.gap = "4px";
  row.style.marginBottom = "4px";
  row.innerHTML = '<input type="text" class="hk" placeholder="key" value="' + esc(k || "") + '" style="flex:1">'
    + '<input type="text" class="hv" placeholder="value" value="' + esc(v || "") + '" style="flex:1">'
    + '<button class="btn sm danger" type="button">✕</button>';
  row.querySelector("button").addEventListener("click", function () { row.remove(); });
  box.appendChild(row);
}

function previewProduce() {
  const topic = document.getElementById("p-topic").value.trim();
  if (!topic) { toast("请填写 topic", "warn"); return; }
  let payload;
  try { payload = JSON.parse(document.getElementById("p-payload").value); }
  catch { toast("payload 不是合法 JSON", "err"); return; }
  const key = document.getElementById("p-key").value.trim() || null;
  const partitionRaw = document.getElementById("p-partition").value;
  const partition = partitionRaw === "" ? null : Number(partitionRaw);
  const reason = document.getElementById("p-reason").value.trim();
  const headers = headersObject();
  const target = document.getElementById("p-preview-box");
  startMutation(target, {
    previewUrl: "/api/kafka/produce/preview",
    executeUrl: "/api/kafka/produce/execute",
    title: "生产消息",
    body: function () { return { topic: topic, key: key, partition: partition, headers: headers, payload: payload, reason: reason }; },
    onDone: function (result) {
      if (result && result.offset !== undefined) {
        document.getElementById("p-preview-box").innerHTML = '<div class="row"><span class="badge b-ok">delivered</span>'
          + '<span class="mono">partition=' + result.partition + " offset=" + result.offset + "</span></div>";
      }
    },
  });
}

function init() {
  document.getElementById("k-reload").addEventListener("click", function () { loadTopics(true); });
  document.getElementById("g-reload").addEventListener("click", loadGroups);
  document.getElementById("m-topic").addEventListener("change", topicChanged);
  document.getElementById("m-start").addEventListener("change", function () {
    const s = document.getElementById("m-start").value;
    document.getElementById("m-offset-field").hidden = s !== "offset";
    document.getElementById("m-time-field").hidden = s !== "time";
  });
  document.getElementById("m-read").addEventListener("click", readMessages);
  document.getElementById("m-auto").addEventListener("change", function () {
    if (this.checked) { readMessages(); timerM = setInterval(function () { if (!document.hidden) readMessages(); }, 15000); }
    else if (timerM) { clearInterval(timerM); timerM = null; }
  });
  document.getElementById("p-hadd").addEventListener("click", function () {
    const hk = document.getElementById("p-hk"); const hv = document.getElementById("p-hv");
    addHeaderRow(hk.value, hv.value); hk.value = ""; hv.value = "";
  });
  document.getElementById("p-template").addEventListener("click", bizTemplate);
  document.getElementById("p-pretty").addEventListener("click", function () {
    try { document.getElementById("p-payload").value = JSON.stringify(JSON.parse(document.getElementById("p-payload").value), null, 2); }
    catch { toast("不是合法 JSON", "err"); }
  });
  document.getElementById("p-preview").addEventListener("click", previewProduce);
  loadTopics(false);
  loadGroups();
}
init();
