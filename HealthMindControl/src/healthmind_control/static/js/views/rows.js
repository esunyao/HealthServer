// 数据浏览视图：meta 驱动 kind 与筛选，服务端片段分页
import { getJson, toast, $, $$ } from "../main.js";
import { load } from "../hx.js";

let meta = [];

function groupOf(key) {
  if (key.startsWith("nutri_")) return "NutriMemo";
  if (key.startsWith("healthmind_workflow_") || key.startsWith("healthmind_integration_")) return "HealthMind · 集成";
  return "HealthMind · AI";
}

function field(name) {
  return document.querySelector('#rows-filters [name="' + name + '"]') || { value: "" };
}
function fieldWrap(id) { return document.getElementById(id); }

function applyKind() {
  const key = document.getElementById("rows-kind").value;
  const m = meta.find(function (x) { return x.key === key; });
  if (!m) return;
  const map = { analysis: "f-analysis", code: "f-code", service: "f-service", subject_id: "f-subject" };
  Object.keys(map).forEach(function (name) {
    fieldWrap(map[name]).hidden = !m.filters.includes(name);
    field(name).value = "";
  });
  field("status").value = "";
  document.getElementById("rows-title").textContent = m.label + " · " + m.table;
  document.getElementById("rows-kind-desc").textContent = "主键 " + m.id_col + "（" + m.id_type + "）· 时间列 " + m.time_col + " · " + m.columns.length + " 列";
}

function queryUrl() {
  const key = document.getElementById("rows-kind").value;
  if (!key) return "";
  const pairs = [["kind", key]];
  ["status", "analysis", "code", "service", "subject_id", "since", "until"].forEach(function (name) {
    const v = field(name).value;
    if (v) pairs.push([name, v]);
  });
  return "/ui/parts/rows?" + pairs.map(function (p) { return encodeURIComponent(p[0]) + "=" + encodeURIComponent(p[1]); }).join("&");
}

function query() { load(document.getElementById("rows-rows"), queryUrl()); }

async function init() {
  try { meta = await getJson("/api/rows/meta"); } catch (e) { toast("加载表清单失败: " + e.message, "err"); return; }
  const sel = document.getElementById("rows-kind");
  const groups = {};
  meta.forEach(function (m) { (groups[groupOf(m.key)] = groups[groupOf(m.key)] || []).push(m); });
  Object.keys(groups).forEach(function (g) {
    const opt = document.createElement("optgroup");
    opt.label = g;
    groups[g].forEach(function (m) {
      const o = document.createElement("option");
      o.value = m.key;
      o.textContent = m.label + "（" + m.table + "）";
      opt.appendChild(o);
    });
    sel.appendChild(opt);
  });
  const wanted = new URLSearchParams(location.search).get("kind");
  if (wanted && meta.some(function (m) { return m.key === wanted; })) sel.value = wanted;
  sel.addEventListener("change", function () { applyKind(); query(); });
  document.getElementById("rows-query").addEventListener("click", query);
  document.getElementById("rows-reset").addEventListener("click", function () {
    ["status", "analysis", "code", "service", "subject_id", "since", "until"].forEach(function (n) { field(n).value = ""; });
    query();
  });
  applyKind();
  query();
}
init();
