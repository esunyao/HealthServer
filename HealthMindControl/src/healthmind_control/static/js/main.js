// HealthMindControl 前端基础：工具函数、全局委托（抽屉/复制/时间）、Toast
const csrfMeta = () => (document.querySelector("meta[name=csrf]") || {}).content || "";

import { renderJsonTreeEl } from "./json-tree.js";

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

export function $(sel, root) { return (root || document).querySelector(sel); }
export function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

export function fmtTs(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("zh-CN", { hour12: false });
}
export function fmtDurMs(ms) {
  if (ms == null) return "-";
  if (ms < 1000) return ms + " ms";
  if (ms < 60000) return (ms / 1000).toFixed(1) + " s";
  return (ms / 60000).toFixed(1) + " min";
}

export async function getJson(url) {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(await errText(r));
  return r.json();
}
export async function postJson(url, body) {
  const payload = { ...(body || {}), csrf_token: body && body.csrf_token !== undefined ? body.csrf_token : csrfMeta() };
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(await errText(r));
  return r.json();
}
async function errText(r) {
  try {
    const data = await r.json();
    return data && (data.detail || data.error) ? String(data.detail || data.error) : r.status + ": " + JSON.stringify(data).slice(0, 300);
  } catch {
    return r.status + ": " + (await r.text()).slice(0, 300);
  }
}

// ---------------- Toast ----------------
export function toast(msg, type) {
  const stack = document.getElementById("toasts");
  if (!stack) { alert(msg); return; }
  const el = document.createElement("div");
  el.className = "toast " + (type || "");
  el.textContent = msg;
  stack.appendChild(el);
  while (stack.children.length > 4) stack.removeChild(stack.firstChild);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; setTimeout(() => el.remove(), 320); }, 5200);
}

// ---------------- 时间本地化 + 委托绑定 ----------------
export function applyTs(root) {
  $$(".ts[data-ts]", root).forEach((el) => {
    const local = fmtTs(el.dataset.ts);
    if (local !== el.textContent.trim()) el.textContent = local;
  });
}

export function bindUi(root) {
  root = root || document;
  applyTs(root);
}

// ---------------- 复制 ----------------
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast("已复制", "ok"); }
  catch { toast("复制失败（浏览器限制）", "err"); }
}

// ---------------- 抽屉 ----------------
let drawerRaw = "";
export function openDrawer(title, payload) {
  const backdrop = document.getElementById("drawer-backdrop");
  const drawer = document.getElementById("drawer");
  document.getElementById("drawer-title").textContent = title || "详情";
  const body = document.getElementById("drawer-body");
  body.replaceChildren();
  drawerRaw = "";
  if (payload instanceof Element) {
    body.appendChild(payload);
  } else if (typeof payload === "string") {
    const pre = document.createElement("pre");
    pre.className = "code";
    pre.textContent = payload;
    body.appendChild(pre);
    drawerRaw = payload;
  } else {
    body.appendChild(renderJsonTreeEl(payload));
    drawerRaw = JSON.stringify(payload, null, 2);
  }
  backdrop.hidden = false;
  document.getElementById("drawer-copy").hidden = !drawerRaw;
  requestAnimationFrame(() => { backdrop.classList.add("open"); drawer.classList.add("open"); });
  body.scrollTop = 0;
}
export function closeDrawer() {
  const backdrop = document.getElementById("drawer-backdrop");
  const drawer = document.getElementById("drawer");
  backdrop.classList.remove("open"); drawer.classList.remove("open");
  setTimeout(() => { backdrop.hidden = true; }, 220);
}

export function openDrawerFromUrl(url, title) {
  openDrawer(title || "加载中…", "加载中…");
  getJson(url).then((data) => openDrawer(title || "详情", data))
    .catch((e) => { openDrawer("详情", "读取失败：" + e.message); });
}

function isIdText(s) { return s && typeof s === "string" && s.length >= 8; }

document.addEventListener("click", async (ev) => {
  const drawerBtn = ev.target.closest("[data-drawer-url]");
  if (drawerBtn) {
    openDrawerFromUrl(drawerBtn.dataset.drawerUrl, drawerBtn.dataset.drawerTitle || "详情");
    return;
  }
  const copyBtn = ev.target.closest("[data-copy]");
  if (copyBtn) { copyText(copyBtn.dataset.copy); return; }
  const drawerClose = ev.target.closest("#drawer-close");
  if (drawerClose) { closeDrawer(); return; }
  const drawerCopy = ev.target.closest("#drawer-copy");
  if (drawerCopy && drawerRaw) { copyText(drawerRaw); return; }
  const backdrop = ev.target.closest("#drawer-backdrop");
  if (backdrop) { closeDrawer(); }
});
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeDrawer(); });

// 监听动态插入的子树
const mo = new MutationObserver((muts) => {
  muts.forEach((m) => m.addedNodes.forEach((node) => { if (node.nodeType === 1) bindUi(node); }));
});
window.addEventListener("DOMContentLoaded", () => { bindUi(document); mo.observe(document.body, { childList: true, subtree: true }); });

export { isIdText };
