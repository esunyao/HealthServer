// 审计视图
import { esc, fmtTs, getJson, toast, $ } from "../main.js";

function detailBtn(row) {
  return '<button class="btn sm ghost" data-audit-detail="' + encodeURIComponent(JSON.stringify(row)) + '">详情</button>';
}
function registerDetails(scope) {
  scope.querySelectorAll("[data-audit-detail]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      import("./../main.js").then(function (mm) {
        let row;
        try { row = JSON.parse(decodeURIComponent(btn.dataset.auditDetail)); } catch { row = btn.dataset.auditDetail; }
        mm.openDrawer("审计详情", row);
      });
    });
  });
}

async function loadActions() {
  const action = document.getElementById("a-action").value.trim();
  const outcome = document.getElementById("a-outcome").value;
  const op = document.getElementById("a-op").value.trim();
  const qs = new URLSearchParams({ limit: "200" });
  if (action) qs.set("action", action);
  if (outcome) qs.set("outcome", outcome);
  if (op) qs.set("operation_id", op);
  const box = document.getElementById("a-list");
  try {
    const rows = await getJson("/api/audit/actions?" + qs.toString());
    if (!rows.length) { box.innerHTML = '<div class="muted">无匹配记录</div>'; return; }
    box.innerHTML = '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>时间</th><th>操作</th><th>对象</th><th>结果</th><th>操作者</th><th>原因</th><th>operation_id</th><th></th></tr></thead><tbody>'
      + rows.map(function (r) {
        return "<tr>"
          + '<td class="time-cell">' + fmtTs(r.occurred_at) + "</td>"
          + '<td><span class="badge b-info">' + esc(r.action) + "</span></td>"
          + '<td class="mono-cell ellip" style="max-width:180px" title="' + esc(r.target || "") + '">' + esc(r.target || "") + "</td>"
          + '<td><span class="badge ' + (r.outcome === "succeeded" ? "b-ok" : r.outcome === "failed" ? "b-err" : "b-warn") + '">' + esc(r.outcome) + "</span></td>"
          + "<td>" + esc(r.actor || "-") + "</td>"
          + '<td class="small ellip" style="max-width:220px" title="' + esc(r.reason || "") + '">' + esc(r.reason || "") + "</td>"
          + '<td class="mono-cell small muted" style="max-width:160px">' + esc(String(r.operation_id || "").slice(0, 14)) + "</td>"
          + "<td>" + detailBtn(r) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    registerDetails(box);
  } catch (e) { toast("查询失败：" + e.message, "err"); }
}

async function loadReleaseAudits() {
  const rid = document.getElementById("ra-release").value.trim();
  const url = rid ? "/api/releases/" + encodeURIComponent(rid) + "/audits" : "/api/audits/releases";
  const box = document.getElementById("ra-list");
  try {
    const rows = await getJson(url);
    if (!rows.length) { box.innerHTML = '<div class="muted">无审计记录</div>'; return; }
    box.innerHTML = '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>时间</th><th>操作</th><th>release</th><th>迁移</th><th>原因</th><th></th></tr></thead><tbody>'
      + rows.map(function (r) {
        return "<tr>"
          + '<td class="time-cell">' + fmtTs(r.occurred_at) + "</td>"
          + '<td><span class="badge ' + (r.action === "promoted" || r.action === "rolled_back" ? "b-ok" : r.action === "retired" ? "b-mut" : "b-info") + '">' + esc(r.action) + "</span></td>"
          + '<td class="mono-cell small">' + esc(String(r.release_id || "").slice(0, 13)) + "… " + esc(r.release_version || "") + "</td>"
          + '<td class="small">' + esc(r.from_status || "-") + " → " + esc(r.to_status) + "</td>"
          + '<td class="small muted ellip" style="max-width:300px" title="' + esc(r.reason || "") + '">' + esc(r.reason || "") + "</td>"
          + "<td>" + detailBtn(r) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    registerDetails(box);
  } catch (e) { toast("查询失败：" + e.message, "err"); }
}

function init() {
  document.getElementById("a-go").addEventListener("click", loadActions);
  document.getElementById("a-clear").addEventListener("click", function () {
    document.getElementById("a-action").value = "";
    document.getElementById("a-outcome").value = "";
    document.getElementById("a-op").value = "";
    loadActions();
  });
  document.getElementById("ra-go").addEventListener("click", loadReleaseAudits);
  loadActions();
}
init();
