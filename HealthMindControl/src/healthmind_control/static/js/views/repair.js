// 受控修复视图
import { esc, fmtTs, getJson, postJson, toast, $ } from "../main.js";
import { startMutation } from "../flow.js";

function recoveryBody(operation, schema, recordId, reason) {
  return { operation: operation, schema_name: schema, record_id: recordId, reason: reason };
}

function manualPreview() {
  const op = document.getElementById("rp-op").value;
  const schema = document.getElementById("rp-schema").value;
  const id = document.getElementById("rp-id").value.trim();
  if (!id) { toast("请填写记录 ID", "warn"); return; }
  const reason = document.getElementById("rp-reason").value.trim();
  const body = recoveryBody(op, schema, id, reason);
  startMutation(document.getElementById("rp-preview-box"), {
    previewUrl: "/api/recovery/preview",
    executeUrl: "/api/recovery/execute",
    body: function () { return body; },
    onDone: function (result) {
      const box = document.getElementById("rp-preview-box");
      box.innerHTML += '<div class="row" style="margin-top:6px"><span class="small muted mono">' + esc(JSON.stringify(result).slice(0, 260)) + "</span></div>";
    },
  });
}

function clonePreview() {
  const task = document.getElementById("ct-task").value.trim();
  if (!task) { toast("请填写 task_id", "warn"); return; }
  const releaseId = document.getElementById("ct-release").value.trim() || null;
  const reason = document.getElementById("ct-reason").value.trim();
  startMutation(document.getElementById("ct-preview-box"), {
    previewUrl: "/api/tasks/" + encodeURIComponent(task) + "/retry/preview",
    executeUrl: "/api/tasks/" + encodeURIComponent(task) + "/retry/execute",
    body: function () { return { release_id: releaseId, reason: reason }; },
    onDone: function (result) {
      const box = document.getElementById("ct-preview-box");
      box.innerHTML += '<div class="row" style="margin-top:6px"><span class="badge b-ok">新任务</span><span class="mono">' + esc(result.task_id || "") + "</span></div>";
    },
  });
}

// ---------------- 一键诊断 ----------------
function suggestionPayload(s) {
  if (s.operation === "clone_task" || s.operation === "clone_task_blocked") {
    return {
      kind: "clone",
      taskId: s.record_id,
      note: s.note,
    };
  }
  return {
    kind: "recovery",
    operation: s.operation,
    schema_name: s.schema_name || "healthmind",
    record_id: s.record_id,
    note: s.note,
    expected_lock_version: s.expected_lock_version ? Number(s.expected_lock_version) : null,
  };
}

function renderGuide(data) {
  const box = document.getElementById("guide-result");
  if (!data || !data.suggestions || !data.suggestions.length) {
    box.innerHTML = '<div class="card warn-line"><div class="muted">未找到可自动建议的修复操作（相关记录见下方结构信息；可在“手动修复”中执行）</div>'
      + '<div style="margin-top:8px"><button class="btn sm" id="guide-raw" type="button">查看原始结构</button></div></div>';
    if (data) {
      const rawBtn = document.getElementById("guide-raw");
      if (rawBtn) rawBtn.addEventListener("click", function () {
        import("./../json-tree.js").then(function (m) {
          import("./../main.js").then(function (mm) { mm.openDrawer("诊断结果（已脱敏）", data.found || {}); });
        });
      });
    }
    return;
  }
  box.innerHTML = '<div class="row" style="margin-bottom:8px"><span class="badge b-info">' + esc(data.query)
    + '</span><span class="small muted">建议按推荐顺序执行；每项执行前都会重新预览并绑定当前记录版本</span></div>'
    + data.suggestions.map(function (s, i) {
      const blocked = s.operation === "clone_task_blocked";
      return '<div class="card" style="padding:12px 14px;margin-bottom:8px">'
        + '<div class="row spread"><b>' + esc(s.label) + "</b>"
        + (blocked ? '<span class="badge b-err">前置校验未通过</span>' : "")
        + '<button class="btn sm ' + (blocked ? "" : "primary") + '" data-sugg="' + i + '"' + (blocked ? " disabled" : "") + ' type="button">执行此修复（先预览）</button></div>'
        + '<div class="small muted" style="margin-top:4px">' + esc(s.note || "") + "</div></div>";
    }).join("") + '<div style="margin-top:4px"><button class="btn sm ghost" id="guide-raw2" type="button">查看原始结构</button></div>';
  const rawBtn = document.getElementById("guide-raw2");
  if (rawBtn) rawBtn.addEventListener("click", function () {
    import("./../main.js").then(function (mm) { mm.openDrawer("诊断结果（已脱敏）", data.found || {}); });
  });
  box.querySelectorAll("[data-sugg]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const s = data.suggestions[Number(btn.dataset.sugg)];
      runSuggestion(s);
    });
  });
}

function runSuggestion(s) {
  const payload = suggestionPayload(s);
  const flowHost = document.createElement("div");
  flowHost.style.marginTop = "8px";
  const card = document.createElement("div");
  card.className = "card";
  card.style.padding = "12px 14px";
  const h = document.createElement("h3");
  h.style.cssText = "margin:0 0 8px;font-size:13.5px";
  h.textContent = s.label;
  card.appendChild(h);
  card.appendChild(flowHost);
  document.getElementById("guide-result").appendChild(card);
  if (payload.kind === "clone") {
    startMutation(flowHost, {
      previewUrl: "/api/tasks/" + encodeURIComponent(payload.taskId) + "/retry/preview",
      executeUrl: "/api/tasks/" + encodeURIComponent(payload.taskId) + "/retry/execute",
      body: function () {
        const reason = window.prompt("克隆任务操作原因（≥3 字符）");
        if (!reason || reason.trim().length < 3) throw new Error("操作原因过短");
        return { release_id: null, reason: reason.trim() };
      },
    });
    return;
  }
  if (s.operation === "recover_attempt" || s.operation === "cancel_task" || s.operation === "reset_outbox"
    || s.operation === "replay_outbox" || s.operation === "replay_nutri_inbox" || s.operation === "replay_hm_inbox") {
    startMutation(flowHost, {
      previewUrl: "/api/recovery/preview",
      executeUrl: "/api/recovery/execute",
      body: function () {
        const reason = window.prompt("修复操作原因（≥3 字符）");
        if (!reason || reason.trim().length < 3) throw new Error("操作原因过短");
        const body = recoveryBody(payload.operation, payload.schema_name, payload.record_id, reason.trim());
        if (payload.expected_lock_version != null) body.expected_lock_version = payload.expected_lock_version;
        return body;
      },
      onDone: function (result) {
        const note = document.createElement("div");
        note.className = "small mono muted";
        note.style.marginTop = "4px";
        note.textContent = JSON.stringify(result).slice(0, 300);
        flowHost.appendChild(note);
      },
    });
    return;
  }
  toast("该建议不支持直接执行（" + s.operation + "）", "warn");
}

async function guide(query) {
  query = (query || "").trim();
  if (query.length < 3) { toast("请输入至少 3 个字符", "warn"); return; }
  const box = document.getElementById("guide-result");
  box.innerHTML = '<div class="muted">诊断中…（只读查询）</div>';
  try { renderGuide(await getJson("/api/repair/plan?query=" + encodeURIComponent(query))); }
  catch (e) { box.innerHTML = '<div class="card"><div class="muted">诊断失败：' + esc(e.message) + "</div></div>"; }
}

function init() {
  document.getElementById("guide-go").addEventListener("click", function () { guide(document.getElementById("guide-q").value); });
  document.getElementById("guide-q").addEventListener("keydown", function (ev) { if (ev.key === "Enter") guide(this.value); });
  document.getElementById("rp-preview").addEventListener("click", manualPreview);
  document.getElementById("ct-preview").addEventListener("click", clonePreview);
  // 从总览等页面带入参数：q / op / schema / id
  const params = new URLSearchParams(location.search);
  const q = params.get("q");
  if (q) { document.getElementById("guide-q").value = q; guide(q); }
  const op = params.get("op");
  if (op) {
    document.getElementById("rp-op").value = op;
    if (params.get("schema")) document.getElementById("rp-schema").value = params.get("schema");
    if (params.get("id")) document.getElementById("rp-id").value = params.get("id");
  }
}
init();
