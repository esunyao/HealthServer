// sse.js —— 全站单例 SSE 客户端：自动连接、指数退避重连、页面隐藏时暂停
// 注意：所有页面共用同一个实例（原来只有总览页启动，导致其他页面一直显示“未连接 SSE”）

class HmcSse {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.retry = 1000;
    this.active = false;
    this._open = false;
    this._es = null;
    this._connecting = false;
    this._retryTimer = null;
  }
  on(event, fn) { (this.listeners[event] = this.listeners[event] || []).push(fn); }
  start() {
    if (this.active) return;
    this.active = true;
    this.connect();
  }
  updateIndicator(text, ok) {
    const el = document.getElementById("sse-state");
    const live = document.getElementById("sse-live");
    if (el) el.textContent = text;
    if (live && live.classList && live.classList.toggle) live.classList.toggle("off", !ok);
  }
  connect() {
    if (!this.active || document.hidden || this._connecting || (this._es && this._open)) return;
    if (typeof EventSource === "undefined") {
      this.updateIndicator("SSE 不可用（浏览器不支持）", false);
      return;
    }
    if (this._es) this._es.close();
    this._connecting = true;
    let es;
    try { es = new EventSource(this.url); this._es = es; } catch (e) { this._connecting = false; this.schedule(); return; }
    const setState = (text, ok) => this.updateIndicator(text, ok);
    es.addEventListener("open", () => { if (this._es !== es) return; this._connecting = false; this._open = true; this.retry = 1000; setState("SSE 已连接", true); });
    es.addEventListener("status", (ev) => {
      if (this._es !== es) return;
      let data;
      try { data = JSON.parse(ev.data); } catch { return; }
      (this.listeners.status || []).forEach((fn) => { try { fn(data); } catch (e) { console.error(e); } });
    });
    es.onerror = () => {
      if (this._es !== es) return;
      es.close();
      this._es = null;
      this._connecting = false;
      this._open = false;
      setState("SSE 重连中…", false);
      this.schedule();
    };
  }
  schedule() {
    if (!this.active || this._retryTimer) return;
    this._retryTimer = setTimeout(() => {
      this._retryTimer = null;
      if (!document.hidden) this.connect();
    }, this.retry);
    this.retry = Math.min(this.retry * 2, 30000);
  }
  stop() {
    this.active = false;
    if (this._retryTimer) clearTimeout(this._retryTimer);
    this._retryTimer = null;
    if (this._es) this._es.close();
    this._es = null;
    this._open = false;
    this._connecting = false;
  }
}
document.addEventListener("visibilitychange", () => {
  if (hmcSse && document.hidden) {
    if (hmcSse._retryTimer) clearTimeout(hmcSse._retryTimer);
    hmcSse._retryTimer = null;
    if (hmcSse._es) hmcSse._es.close();
    hmcSse._es = null;
    hmcSse._open = false;
    hmcSse._connecting = false;
  } else if (hmcSse && hmcSse.active) {
    hmcSse.retry = 1000;
    hmcSse.connect();
  }
});
export const hmcSse = new HmcSse("/api/events");

let started = false;

/** 全站启动 SSE（幂等）：任何页面加载即连接，保持页脚状态指示准确。 */
export function ensureSse() {
  if (started) return hmcSse;
  started = true;
  hmcSse.start();
  return hmcSse;
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ensureSse);
  else ensureSse();
}
