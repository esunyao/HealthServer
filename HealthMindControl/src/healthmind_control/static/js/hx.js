// hx.js —— htmx 风格轻量驱动（属性与官方 htmx 同名，可无痛替换 vendor/htmx.min.js）
// 支持：hx-get / hx-trigger(click|load|change) / hx-target / hx-swap(innerHTML|append|outerHTML)
//       hx-include(选择器或 closest form) / hx-indicator('self' 或选择器) / hx-push-url
import { errText, toast } from "./main.js";

function valueOf(input) {
  if (input.type === "checkbox") return input.checked ? (input.value || "on") : null;
  if (input.type === "radio") return input.checked ? input.value : null;
  return input.value != null ? String(input.value) : "";
}

function serialize(root, form) {
  const els = form
    ? Array.from(form.querySelectorAll("input,select,textarea"))
    : [root];
  const pairs = [];
  els.forEach((input) => {
    if (input.disabled || !input.name) return;
    const v = valueOf(input);
    if (v === null) return;
    pairs.push(encodeURIComponent(input.name) + "=" + encodeURIComponent(v));
  });
  return pairs.join("&");
}

function resolveInclude(el, spec) {
  if (!spec) return null;
  const trimmed = spec.trim();
  if (trimmed.startsWith("closest")) {
    const sel = trimmed.replace(/^closest\s*/, "");
    return el.closest(sel);
  }
  if (trimmed.startsWith("find ")) {
    return el.querySelector(trimmed.replace(/^find\s*/, ""));
  }
  return document.querySelector(trimmed);
}

async function perform(el) {
  if (el.dataset.hxBusy) return;
  let url = el.getAttribute("hx-get");
  if (!url) return;
  const form = resolveInclude(el, el.getAttribute("hx-include"));
  const qs = form ? serialize(el, form) : "";
  if (qs) url += (url.includes("?") ? "&" : "?") + qs;
  const targetSel = el.getAttribute("hx-target");
  // 未显式声明 hx-target 时默认就地渲染（容器自身 hx-get + hx-trigger="load" 的常见场景）
  const target = targetSel ? document.querySelector(targetSel) : el;
  const swap = el.getAttribute("hx-swap") || "innerHTML";
  const indicator = el.getAttribute("hx-indicator");
  const busy = indicator === "self" || indicator === null;
  el.dataset.hxBusy = "1";
  if (busy) el.disabled = true;
  const indEl = indicator && indicator !== "self" ? document.querySelector(indicator) : null;
  if (indEl) indEl.hidden = false;
  try {
    const r = await fetch(url, { headers: { Accept: "text/html" } });
    if (!r.ok) {
      throw new Error(await errText(r));
    }
    const html = await r.text();
    if (swap === "none") return;
    if (!target) { toast("hx-target 未找到：" + targetSel, "err"); return; }
    if (swap === "append") {
      const holder = document.createElement("div");
      holder.innerHTML = html;
      Array.from(holder.children).forEach((child) => target.appendChild(child));
    } else if (swap === "outerHTML") {
      const holder = document.createElement("div");
      holder.innerHTML = html;
      target.replaceWith(holder.firstElementChild || holder.firstChild);
    } else {
      target.innerHTML = html;
    }
    const push = el.getAttribute("hx-push-url");
    if (push === "true") history.pushState({}, "", url.split("?")[0] + "?" + qs);
    else if (push) history.pushState({}, "", push);
    window.dispatchEvent(new CustomEvent("hmc:afterSwap", { detail: { target } }));
  } catch (err) {
    toast("加载失败：" + err.message, "err");
    // 容器型加载失败时把错误写回原位，避免页面一直停在“载入中…”
    if (target && swap === "innerHTML") {
      const box = document.createElement("div");
      box.className = "muted";
      box.textContent = "加载失败：" + err.message;
      target.replaceChildren(box);
    }
  } finally {
    delete el.dataset.hxBusy;
    if (busy) el.disabled = false;
    if (indEl) indEl.hidden = true;
  }
}

export function scan(root) {
  (root || document).querySelectorAll("[hx-get]").forEach((el) => {
    const trigger = el.getAttribute("hx-trigger") || "click";
    if (trigger === "load") {
      if (el.dataset.hxLoaded) return;
      el.dataset.hxLoaded = "1";
      perform(el);
      return;
    }
    if (el.dataset.hxBound) return;
    el.dataset.hxBound = "1";
    el.addEventListener(trigger === "change" ? "change" : "click", (ev) => {
      ev.preventDefault();
      perform(el);
    });
  });
}

export function load(el, url) {
  el.setAttribute("hx-get", url);
  delete el.dataset.hxLoaded;
  perform(el);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => scan(document));
} else {
  scan(document);
}
window.addEventListener("hmc:afterSwap", (e) => scan(e.detail.target));
