// 总览视图：健康卡 / 任务统计 / 生产版本 / 滞留 / Kafka 概览
import { esc, fmtTs, fmtDurMs, getJson, toast, $$ } from "../main.js";
import { hmcSse } from "../sse.js";

const OK_WORDS = ["succeeded", "processed", "published", "completed", "active", "ok", "confirmed", "healthy"];
const WARN_WORDS = ["pending", "queued", "publishing", "processing", "analysing", "running", "ready_for_analysis", "created", "uploading", "cancelled"];
const ERR_WORDS = ["failed", "timed_out", "expired", "denied", "error", "stale", "unavailable"];

export function badgeCls(status) {
  const v = String(status || "").toLowerCase();
  if (OK_WORDS.includes(v)) return "b-ok";
  if (ERR_WORDS.includes(v)) return "b-err";
  if (WARN_WORDS.includes(v)) return "b-warn";
  return "b-info";
}
export function badgeHtml(text) {
  return '<span class="badge ' + badgeCls(text) + '">' + esc(text) + "</span>";
}

const serviceMeta = [
  ["database", "PostgreSQL"], ["kafka", "Kafka"], ["dify", "Dify"],
  ["mcp", "MCP"], ["auth", "Authentik"],
];

function svcDesc(key, svc) {
  if (!svc) return "不可用";
  if (svc.error) return String(svc.error);
  if (key === "kafka") {
    const brokers = (svc.brokers || []).length;
    return brokers ? brokers + " broker(s), " + (svc.topics || []).length + " topics" : "无 broker";
  }
  if (svc.status) return "HTTP " + svc.status;
  return svc.ok ? "正常" : "不可用";
}

function healthCards(s) {
  const host = document.getElementById("health-cards");
  host.innerHTML = serviceMeta.map(function (pair) {
    const key = pair[0], label = pair[1];
    const svc = s[key];
    const ok = !!(svc && svc.ok);
    const sub = key === "database" ? "write=" + (svc && svc.write_enabled) : svcDesc(key, svc);
    return '<div class="health ' + (ok ? "ok" : "err") + '">'
      + '<div class="name">' + label + "</div>"
      + '<div class="meta">' + esc(sub) + "</div>"
      + (key === "database" && svc && svc.schema_error ? '<div class="meta" style="color:var(--err)">' + esc(svc.schema_error) + "</div>" : "")
      + "</div>";
  }).join("");
}

function taskStats(tasks) {
  const box = document.getElementById("task-stats");
  const color = { succeeded: "ok", failed: "err", running: "info", queued: "warn", cancelled: "mut", expired: "mut" };
  box.innerHTML = (tasks || []).map(function (t) {
    return '<div class="stat ' + (color[t.status] || "mut") + '"><b>' + t.count + "</b><span>" + esc(t.status) + "</span></div>";
  }).join("");
  $$(".stat", box).forEach(function (el) { el.addEventListener("animationend", function () { el.classList.remove("flash"); }); });
}

function productionCard(p) {
  const box = document.getElementById("production-card");
  if (!p) { box.innerHTML = '<div class="muted">没有 production 版本（尚未发布或数据缺失）</div>'; return; }
  const tools = (p.tools || []).map(function (t) {
    return '<span class="badge b-accent" title="scope: ' + esc(t.scope || "") + '">' + esc(t.tool_code || "") + "</span>";
  }).join("");
  const row = function (k, v, mono) {
    return '<tr><td class="muted" style="width:150px">' + k + "</td><td class=\"mono-cell\">" + (mono === false ? esc(v) : '<span class="mono-cell ellip" title="' + esc(v) + '">' + esc(v) + "</span>") + "</td></tr>";
  };
  box.innerHTML = '<table class="tbl" style="font-size:12.5px">'
    + row("release", p.release_version, false)
    + row("app / workflow", p.dify_app_id + " / " + p.dify_workflow_id, false)
    + row("workflow version", p.dify_workflow_version, false)
    + row("schema sha", "in " + String(p.input_schema_sha256 || "").slice(0, 10) + "…  out " + String(p.output_schema_sha256 || "").slice(0, 10) + "…", false)
    + row("promoted", fmtTs(p.promoted_at), false)
    + "</table>"
    + '<div class="row" style="margin-top:8px">' + tools + "</div>"
    + '<div class="small muted" style="margin-top:6px">' + esc(p.task_type_code) + " · release " + esc(p.release_id) + "</div>";
}

function failures(failures) {
  const tbody = document.getElementById("recent-failures");
  if (!failures || !failures.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">暂无失败任务</td></tr>';
    return;
  }
  tbody.innerHTML = failures.map(function (f) {
    return "<tr>"
      + '<td class="time-cell">' + fmtTs(f.completed_at) + "</td>"
      + '<td class="mono-cell ellip" style="max-width:210px">' + esc(String(f.task_id || "").slice(0, 18)) + "</td>"
      + '<td><span class="badge b-err">' + esc(f.failure_code || "-") + "</span></td>"
      + '<td class="num">' + fmtDurMs(f.duration_ms) + "</td>"
      + '<td class="mono-cell ellip" style="max-width:280px" title="' + esc(f.failure_message || "") + '">' + esc(f.failure_message || "") + "</td>"
      + "</tr>";
  }).join("");
}

// 完整状态缓存：SSE 轻量摘要只覆盖 DB/任务区，不得冲掉 kafka/dify/mcp/auth 服务卡
let lastFull = null;

export function applySummary(s) {
  if (!s || s.error) { toast("SSE 摘要异常", "err"); return; }
  const hasServices = s.kafka !== undefined || s.dify !== undefined || s.mcp !== undefined || s.auth !== undefined;
  if (hasServices) {
    lastFull = s;                       // /api/status 完整负载
  } else if (lastFull) {
    lastFull = { ...lastFull, database: s.database, tasks: s.tasks, production: s.production, recent_failures: s.recent_failures };
  } else {
    lastFull = s;                       // 尚无完整负载（理论上不会走到）
  }
  const merged = lastFull;
  const host = document.getElementById("health-cards");
  if (host && (merged.kafka === undefined && merged.dify === undefined)) {
    host.innerHTML = '<div class="muted">完整服务状态尚未加载——请点右上“刷新服务”</div>';
  } else {
    healthCards(merged);
  }
  if (merged.database && merged.database.available === false) {
    const taskBox = document.getElementById("task-stats");
    if (taskBox) taskBox.innerHTML = '<div class="muted">数据库暂不可用，统计已暂停（不是 0 条）</div>';
    const prodBox = document.getElementById("production-card");
    if (prodBox) prodBox.innerHTML = '<div class="muted">数据库恢复并完成 Schema 校验后自动刷新</div>';
    const failureBox = document.getElementById("recent-failures");
    if (failureBox) failureBox.innerHTML = '<tr><td colspan="5" class="empty">数据库暂不可用，未返回失败任务统计</td></tr>';
    return;
  }
  taskStats(merged.tasks);
  if (document.getElementById("production-card")) productionCard(merged.production);
  if (document.getElementById("recent-failures")) failures(merged.recent_failures);
  document.getElementById("task-summary-time").textContent = "更新于 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

// ---------------- 滞留 ----------------
const sectionMeta = [
  ["stale", "滞留（queued/running 任务与 failed/publishing 出件箱）"],
  ["attempts_stale", "超时仍 running 的 attempt"],
  ["inbox_stale", "processing 滞留的收件箱"],
  ["unconsumed", "已发布但下游未出现（发布未消费）"],
  ["inconsistent", "餐食/会话与 AI 任务状态不一致"],
];

function backlogTables(b) {
  const box = document.getElementById("backlog-body");
  if (!b) { box.innerHTML = '<div class="muted">加载失败</div>'; return; }
  if (b.available === false) {
    box.innerHTML = '<div class="empty"><b>数据库暂不可用</b><br><span class="muted">'
      + esc(b.error || "后台正在自动重连") + '；当前没有返回统计，不代表零滞留。</span></div>';
    return;
  }
  const parts = [];
  const chips = (b.counts || []).map(function (c) {
    return '<span class="badge ' + (c.status === "failed" || c.status === "publishing" ? "b-err" : c.status === "processed" || c.status === "published" ? "b-ok" : "b-warn") + '">'
      + esc(c.source) + " · " + esc(c.status) + " <b>" + c.count + "</b></span>";
  });
  parts.push('<div class="row" style="margin-bottom:10px">' + chips.join("") + "</div>");
  sectionMeta.forEach(function (pair) {
    const key = pair[0], label = pair[1];
    const rows = b[key] || [];
    parts.push('<h2 class="section">' + esc(label) + ' <span class="hint">' + rows.length + " 条</span></h2>");
    parts.push(rows.length ? renderBacklogTable(key, rows) : '<div class="muted small" style="margin:4px 0 10px">无</div>');
  });
  box.innerHTML = parts.join("");
}

function drawerUrlFor(key, row) {
  if (key === "stale") {
    if (row.kind === "task") return { url: "/api/rows/healthmind_ai_tasks/" + row.id, repair: row.id };
    return { url: "/api/rows/" + (row.schema_name === "nutri" ? "nutri_integration_outbox" : "healthmind_integration_outbox") + "/" + row.id, repair: row.id };
  }
  if (key === "attempts_stale") return { url: "/api/rows/healthmind_ai_task_attempts/" + row.id, repair: row.id };
  if (key === "inbox_stale") {
    const kind = String(row.source).startsWith("healthmind") ? "healthmind_integration_inbox" : "nutri_integration_inbox";
    return { url: "/api/rows/" + kind + "/" + row.id, repair: row.id };
  }
  if (key === "unconsumed") {
    const kind = String(row.source).startsWith("hm") ? "healthmind_integration_outbox" : "nutri_integration_outbox";
    return { url: "/api/rows/" + kind + "/" + row.id, repair: row.id };
  }
  return { url: "/api/rows/nutri_meal_records/" + row.meal_id, repair: row.meal_id };
}

function renderBacklogTable(key, rows) {
  const headMap = {
    stale: ["来源", "ID", "状态", "时间", "操作"],
    attempts_stale: ["attempt", "task", "次数", "任务状态", "超时点", "操作"],
    inbox_stale: ["来源", "ID", "状态", "时间", "操作"],
    unconsumed: ["来源", "事件 ID", "类型", "发布时间", "目标 topic", "操作"],
    inconsistent: ["meal", "会话", "分析状态", "会话状态", "任务状态", "操作"],
  };
  const heads = headMap[key];
  const rowsHtml = rows.map(function (r) {
    const link = drawerUrlFor(key, r);
    const cells = [];
    if (key === "stale") {
      cells.push(esc(r.source), '<span class="mono-cell ellip" style="max-width:170px" title="' + esc(r.id) + '">' + esc(String(r.id).slice(0, 16)) + "</span>", badgeHtml(r.status), fmtTs(r.at));
    } else if (key === "attempts_stale") {
      cells.push('<span class="mono-cell">' + esc(String(r.id).slice(0, 12)) + "</span>", esc(String(r.task_id).slice(0, 12)), String(r.attempt_no), badgeHtml(r.task_status), fmtTs(r.deadline));
    } else if (key === "inbox_stale") {
      cells.push(esc(r.source), '<span class="mono-cell ellip" style="max-width:170px" title="' + esc(r.id) + '">' + esc(String(r.id).slice(0, 16)) + "</span>", badgeHtml(r.status), fmtTs(r.at));
    } else if (key === "unconsumed") {
      cells.push(esc(r.source), '<span class="mono-cell ellip" style="max-width:170px" title="' + esc(r.id) + '">' + esc(String(r.id).slice(0, 16)) + "</span>", '<span class="badge b-warn">' + esc(r.event_type || "-") + "</span>", fmtTs(r.published_at), esc(r.destination_key || "-"));
    } else {
      cells.push(String(r.meal_id), String(r.capture_session_id).slice(0, 12), badgeHtml(r.analysis_status), badgeHtml(r.capture_status), r.task_status ? badgeHtml(r.task_status) : '<span class="muted">无任务</span>');
    }
    const repairHref = key === "unconsumed" && String(r.source).startsWith("hm")
      ? "/ui/repair?op=replay_outbox&schema=healthmind&id=" + encodeURIComponent(r.id)
      : "/ui/repair?q=" + encodeURIComponent(link.repair);
    cells.push('<div class="row-actions"><button class="btn sm" data-drawer-url="' + link.url + '" data-drawer-title="详情">详情</button>'
      + '<a class="btn sm ghost" href="' + repairHref + '">修复</a></div>');
    return "<tr>" + cells.map(function (c) { return "<td>" + c + "</td>"; }).join("") + "</tr>";
  }).join("");
  return '<div class="tbl-wrap"><table class="tbl"><thead><tr>' + heads.map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("") + "</tr></thead><tbody>" + rowsHtml + "</tbody></table></div>";
}

async function refreshBacklogs() {
  try {
    const b = await getJson("/api/backlogs");
    backlogTables(b);
  } catch (e) { toast("滞留数据加载失败: " + e.message, "err"); }
}

// ---------------- Kafka 概览 ----------------
async function refreshKafka() {
  try {
    const [meta, groups] = await Promise.all([getJson("/api/kafka/topics"), getJson("/api/kafka/groups")]);
    const box = document.getElementById("kafka-overview");
    if (!meta.topics || !meta.topics.length) { box.innerHTML = '<div class="muted">无可见 topic</div>'; return; }
    const biz = meta.topics.filter(function (t) {
      return ["nutrition-capture-ready", "nutrition-analysis-completed", "nutrition-analysis-failed"].includes(t.name);
    });
    const unhealth = [];
    (meta.topics || []).forEach(function (t) {
      (t.partitions || []).forEach(function (p) {
        if (!p.healthy) unhealth.push(t.name + "/" + p.partition);
      });
    });
    const bizHtml = biz.map(function (t) {
      const parts = t.partitions.map(function (p) {
        return '<span class="badge ' + (p.healthy ? "b-ok" : "b-err") + '" title="partition ' + p.partition + " leader=" + p.leader + ' replicas=[' + (p.replicas || []).join(",") + "] isr=[" + (p.isrs || []).join(",") + ']">p' + p.partition + "</span>";
      }).join("");
      return '<tr><td class="mono-cell">' + esc(t.name) + "</td><td>" + parts + "</td><td class=\"num\">" + t.partitions.length + "</td></tr>";
    }).join("");
    const groupRows = (groups || []).filter(function (g) { return !String(g.group_id).startsWith("healthmind-control-"); })
      .slice(0, 12).map(function (g) {
        return '<tr><td class="mono-cell">' + esc(g.group_id) + "</td><td>" + esc(g.state) + "</td><td class=\"num\">" + (g.members || []).length + "</td><td class=\"num\" style=\"color:" + ((g.lag || 0) > 0 ? "var(--warn)" : "var(--ok)") + '">' + (g.lag || 0) + "</td></tr>";
      }).join("");
    box.innerHTML =
      '<div class="tbl-wrap" style="margin-bottom:10px"><table class="tbl"><thead><tr><th>业务 topic</th><th>分区（leader/ISR 健康）</th><th style="text-align:right">分区数</th></tr></thead><tbody>' + (bizHtml || '<tr><td colspan="3" class="empty">业务 topic 未发现</td></tr>') + "</tbody></table></div>"
      + (unhealth.length ? '<div class="row" style="margin-bottom:8px"><span class="badge b-err">异常分区</span>' + unhealth.slice(0, 20).map(function (u) { return '<span class="badge b-err">' + esc(u) + "</span>"; }).join("") + "</div>" : "")
      + '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>消费组（前 12）</th><th>状态</th><th style="text-align:right">成员</th><th style="text-align:right">总 lag</th></tr></thead><tbody>' + (groupRows || '<tr><td colspan="4" class="empty">无消费组</td></tr>') + "</tbody></table></div>";
  } catch (e) { toast("Kafka 概览加载失败: " + e.message, "err"); }
}

function autoTimer(el, fn, ms) {
  let timer = null;
  el.addEventListener("change", function () {
    if (el.checked) { fn(); timer = setInterval(function () { if (!document.hidden) fn(); }, ms); }
    else if (timer) { clearInterval(timer); timer = null; }
  });
}

export function initDashboard() {
  getJson("/api/status").then(function (s) {
    applySummary(s);
  }).catch(function (e) { toast("状态加载失败: " + e.message, "err"); });
  hmcSse.on("status", applySummary);   // 连接由 sse.js 的 ensureSse() 全站启动（幂等），此处只订阅
  document.getElementById("btn-health-refresh").addEventListener("click", function () {
    getJson("/api/status").then(applySummary).catch(function (e) { toast(e.message, "err"); });
  });
  document.getElementById("btn-backlog-refresh").addEventListener("click", refreshBacklogs);
  document.getElementById("btn-kafka-refresh").addEventListener("click", refreshKafka);
  autoTimer(document.getElementById("backlog-auto"), refreshBacklogs, 30000);
  autoTimer(document.getElementById("kafka-auto"), refreshKafka, 30000);
  refreshBacklogs();
}
initDashboard();
