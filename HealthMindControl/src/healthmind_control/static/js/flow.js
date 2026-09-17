// flow.js —— 统一“预览 → 原因/确认文本 → 执行”的受控变更流
import { esc, fmtTs, getJson, postJson, toast, openDrawer, $$ } from "./main.js";

function renderRepreview(container, opts, message) {
  container.innerHTML = '<div class="row"><span class="badge b-warn">需要重新预览</span>'
    + '<span class="small muted">' + esc(message) + '</span>'
    + '<button class="btn sm" data-flow-role="repreview" type="button">重新预览</button></div>';
  container.querySelector('[data-flow-role="repreview"]').addEventListener("click", function () {
    startMutation(container, opts);
  });
}

async function recoverByAudit(operationId) {
  if (!operationId) return null;
  const rows = await getJson("/api/audit/actions?limit=10&operation_id=" + encodeURIComponent(operationId));
  if (!Array.isArray(rows) || !rows.length) return null;
  return rows.find(function (row) { return row.outcome === "succeeded"; })
    || rows.find(function (row) { return row.outcome === "failed"; })
    || rows[0];
}

export function buildSummary(res) {
  const lines = [];
  const skip = new Set(["preview_token", "snapshot", "confirmation", "expires_at", "warnings", "requires_force", "message"]);
  Object.keys(res || {}).forEach(function (k) {
    if (skip.has(k)) return;
    let v = res[k];
    if (typeof v === "object") v = JSON.stringify(v).slice(0, 160);
    lines.push('<div class="row" style="gap:6px"><span class="muted small" style="min-width:130px">' + esc(k) + '</span><span class="mono small ellip" style="flex:1" title="' + esc(String(v)) + '">' + esc(String(v)) + "</span></div>");
  });
  return lines.join("");
}

export function startMutation(container, opts) {
  // opts: { previewUrl, executeUrl, body():object, onPreview?:fn, onDone(result), note?, title? }
  container.innerHTML = '<div class="muted">预览中…</div>';
  let body;
  try {
    body = opts.body();
    if (!body || !body.reason || String(body.reason).trim().length < 3) {
      toast("请先填写操作原因（≥3 字符）", "warn");
      container.innerHTML = "";
      return;
    }
  } catch (e) { container.innerHTML = ""; toast("参数错误：" + e.message, "err"); return; }

  postJson(opts.previewUrl, body).then(function (res) {
    const warnings = res.warnings || [];
    const snapshot = res.snapshot;
    let html = "";
    html += '<div class="row" style="margin-bottom:6px">'
      + (warnings.length ? warnings.map(function (w) { return '<span class="badge b-err">' + esc(w) + "</span>"; }).join("") : '<span class="badge b-ok">结构校验通过</span>')
      + '<span class="small muted">确认文本：<b>' + esc(res.confirmation) + "</b></span></div>";
    html += buildSummary(res);
    if (res.message) {
      html += '<div class="row" style="margin-top:4px"><span class="badge b-info">将发送到 ' + esc(res.message.topic || "") + " key=" + esc(res.message.key || "-") + "</span></div>";
    }
    if (snapshot) {
      html += '<div class="row" style="margin-top:4px"><button class="btn sm ghost" data-flow-role="snapshot" type="button">查看将变更的记录快照</button></div>';
    }
    if (warnings.length && res.requires_force) {
      html += '<label class="check-line" style="margin:8px 0"><input type="checkbox" data-flow-role="force"> 强制执行带警告的操作</label>';
    }
    html += '<div class="field" style="margin:8px 0"><label>输入确认文本（预览后 2 分钟内有效，记录若被改动会要求重新预览）</label>'
      + '<input type="text" data-flow-role="confirm" placeholder="' + esc(res.confirmation || "") + '" autocomplete="off"></div>';
    html += '<div class="row"><button class="btn danger" data-flow-role="run" type="button">执行</button>'
      + '<button class="btn ghost" data-flow-role="cancel" type="button">取消</button>'
      + '<span class="small muted">预览过期于 ' + fmtTs(res.expires_at) + "</span></div>";
    container.innerHTML = html;
    if (snapshot) {
      container.querySelector('[data-flow-role="snapshot"]').addEventListener("click", function () { openDrawer("预览快照（已脱敏）", snapshot); });
    }
    container.querySelector('[data-flow-role="cancel"]').addEventListener("click", function () { container.innerHTML = ""; });
    container.querySelector('[data-flow-role="run"]').addEventListener("click", function () {
      const confirmText = container.querySelector('[data-flow-role="confirm"]').value;
      const forceEl = container.querySelector('[data-flow-role="force"]');
      const force = !!(forceEl && forceEl.checked);
      const run = container.querySelector('[data-flow-role="run"]');
      if (run.disabled) return;
      run.disabled = true;
      postJson(opts.executeUrl, {
        preview_token: res.preview_token,
        confirmation: confirmText,
        accept_warnings: force,
      }).then(function (result) {
        container.innerHTML = '<div class="row"><span class="badge b-ok">执行成功</span><span class="mono small ellip">' + esc(JSON.stringify(result).slice(0, 220)) + "</span></div>";
        toast("执行成功", "ok");
        if (opts.onDone) opts.onDone(result);
      }).catch(function (err) {
        const operationId = err.operationId || res.operation_id;
        if (err.code === "CONFIRMATION_MISMATCH" || err.code === "WARNINGS_NOT_ACCEPTED") {
          toast("执行失败：" + err.message, "err");
          run.disabled = false;
          const confirm = container.querySelector('[data-flow-role="confirm"]');
          if (confirm) confirm.focus();
          return;
        }
        if (err.requiresRepreview || err.code === "PREVIEW_EXPIRED" || err.code === "PREVIEW_STALE") {
          renderRepreview(container, opts, err.message);
          toast(err.message, "warn");
          return;
        }
        if (!err.status || err.code === "PREVIEW_EXECUTING" || err.code === "EXECUTION_INDETERMINATE") {
          recoverByAudit(operationId).then(function (audit) {
            if (audit && audit.outcome === "succeeded") {
              const recovered = (audit.details && (audit.details.result || audit.details.after)) || audit;
              container.innerHTML = '<div class="row"><span class="badge b-ok">执行已成功</span>'
                + '<span class="small muted">已通过审计恢复结果，操作编号 ' + esc(operationId || "-") + '</span></div>';
              toast("操作已成功（通过审计确认）", "ok");
              if (opts.onDone) opts.onDone(recovered);
            } else if (audit && audit.outcome === "failed"
              && audit.details && audit.details.no_side_effect === true) {
              renderRepreview(container, opts, "审计确认执行失败，请重新预览后再试。操作编号 " + (operationId || "-"));
              toast("执行失败，审计中未发现成功副作用", "err");
            } else {
              container.innerHTML = '<div class="row"><span class="badge b-err">结果未知</span>'
                + '<span class="small muted">请检查目标记录和审计，不会自动重复执行。操作编号 '
                + esc(operationId || "-") + '</span></div>';
              toast("执行结果未知，已停止自动重试", "err");
            }
          }).catch(function () {
            container.innerHTML = '<div class="row"><span class="badge b-err">结果未知</span>'
              + '<span class="small muted">无法读取审计，请检查目标记录。操作编号 '
              + esc(operationId || "-") + '</span></div>';
          });
          return;
        }
        toast("执行失败：" + err.message, "err");
        run.disabled = !err.canRetry;
      });
    });
    if (opts.onPreview) opts.onPreview(res);
  }).catch(function (err) {
    container.innerHTML = "";
    toast("预览失败：" + err.message, "err");
  });
}
