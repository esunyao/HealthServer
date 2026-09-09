// flow.js —— 统一“预览 → 原因/确认文本 → 执行”的受控变更流
import { esc, fmtTs, getJson, postJson, toast, openDrawer, $$ } from "./main.js";

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
      html += '<div class="row" style="margin-top:4px"><button class="btn sm ghost" id="flow-snap" type="button">查看将变更的记录快照</button></div>';
    }
    if (warnings.length && res.requires_force) {
      html += '<label class="check-line" style="margin:8px 0"><input type="checkbox" id="flow-force"> 强制执行带警告的操作</label>';
    }
    html += '<div class="field" style="margin:8px 0"><label>输入确认文本（预览后 2 分钟内有效，记录若被改动会要求重新预览）</label>'
      + '<input type="text" id="flow-confirm" placeholder="' + esc(res.confirmation || "") + '" autocomplete="off"></div>';
    html += '<div class="row"><button class="btn danger" id="flow-run" type="button">执行</button>'
      + '<button class="btn ghost" id="flow-cancel" type="button">取消</button>'
      + '<span class="small muted">预览过期于 ' + fmtTs(res.expires_at) + "</span></div>";
    container.innerHTML = html;
    if (snapshot) {
      document.getElementById("flow-snap").addEventListener("click", function () { openDrawer("预览快照（已脱敏）", snapshot); });
    }
    document.getElementById("flow-cancel").addEventListener("click", function () { container.innerHTML = ""; });
    document.getElementById("flow-run").addEventListener("click", function () {
      const confirmText = document.getElementById("flow-confirm").value;
      const forceEl = document.getElementById("flow-force");
      const force = !!(forceEl && forceEl.checked);
      const run = document.getElementById("flow-run");
      run.disabled = true;
      postJson(opts.executeUrl, {
        ...body,
        preview_token: res.preview_token,
        confirmation: confirmText,
        force: force,
      }).then(function (result) {
        container.innerHTML = '<div class="row"><span class="badge b-ok">执行成功</span><span class="mono small ellip">' + esc(JSON.stringify(result).slice(0, 220)) + "</span></div>";
        toast("执行成功", "ok");
        if (opts.onDone) opts.onDone(result);
      }).catch(function (err) {
        toast("执行失败：" + err.message, "err");
        run.disabled = false;
      });
    });
    if (opts.onPreview) opts.onPreview(res);
  }).catch(function (err) {
    container.innerHTML = "";
    toast("预览失败：" + err.message, "err");
  });
}
