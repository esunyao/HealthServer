// 关于视图
import { esc, getJson } from "../main.js";

const serviceMeta = [
  ["database", "PostgreSQL"], ["kafka", "Kafka"], ["dify", "Dify"], ["mcp", "MCP"], ["auth", "Authentik"],
];

async function init() {
  try {
    const s = await getJson("/api/status");
    const rows = serviceMeta.map(function (pair) {
      const svc = s[pair[0]];
      const ok = !!(svc && svc.ok);
      const desc = !svc ? "不可用" : (svc.error || (svc.status ? "HTTP " + svc.status : (pair[0] === "kafka" ? (svc.brokers || []).length + " broker, " + (svc.topics || []).length + " topics" : "正常")));
      return "<tr><td>" + esc(pair[1]) + '</td><td><span class="badge ' + (ok ? "b-ok" : "b-err") + '">' + (ok ? "可达" : "不可达") + "</span> " + esc(desc) + "</td></tr>";
    }).join("");
    const taskTotal = (s.tasks || []).reduce(function (a, t) { return a + t.count; }, 0);
    document.getElementById("ab-status").innerHTML =
      '<div class="tbl-wrap"><table class="tbl"><tbody>' + rows + "</tbody></table></div>"
      + '<div class="small muted" style="margin-top:8px">AI 任务总数 ' + taskTotal
      + (s.production ? " · production " + esc(s.production.release_version) : " · 无 production") + "</div>";
    const pre = document.getElementById("ab-json");
    pre.textContent = JSON.stringify(s, null, 2);
  } catch (e) {
    document.getElementById("ab-status").innerHTML = '<div class="muted">加载失败：' + esc(e.message) + "</div>";
  }
}
init();
