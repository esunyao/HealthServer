// sse.js —— 轻量 SSE 客户端：自动重连（指数退避）、页面隐藏时暂停
import { toast } from "./main.js";

class HmcSse {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.retry = 1000;
    this.active = false;
    this._open = false;
  }
  on(event, fn) { (this.listeners[event] = this.listeners[event] || []).push(fn); }
  start() {
    if (this.active) return;
    this.active = true;
    this.connect();
  }
  connect() {
    if (!this.active || document.hidden) return;
    try { this._es = new EventSource(this.url); } catch (e) { this.schedule(); return; }
    const es = this._es;
    const setState = (text, ok) => {
      const el = document.getElementById("sse-state");
      const live = document.getElementById("sse-live");
      if (el) el.textContent = text;
      if (live) live.classList.toggle("off", !ok);
    };
    es.addEventListener("open", () => { this._open = true; this.retry = 1000; setState("SSE 已连接", true); });
    es.addEventListener("status", (ev) => {
      let data;
      try { data = JSON.parse(ev.data); } catch { return; }
      (this.listeners.status || []).forEach((fn) => { try { fn(data); } catch (e) { console.error(e); } });
    });
    es.onerror = () => {
      es.close();
      this._open = false;
      setState("SSE 重连中…", false);
      this.schedule();
    };
  }
  schedule() {
    if (!this.active) return;
    setTimeout(() => { if (!document.hidden) this.connect(); else this.waitVisible(); }, this.retry);
    this.retry = Math.min(this.retry * 2, 30000);
  }
  waitVisible() {
    const handler = () => {
      document.removeEventListener("visibilitychange", handler);
      this.retry = 1000;
      this.connect();
    };
    document.addEventListener("visibilitychange", handler);
  }
  stop() { this.active = false; if (this._es) this._es.close(); }
}
document.addEventListener("visibilitychange", () => {
  if (hmcSse && document.hidden && hmcSse._es) { hmcSse._es.close(); hmcSse._open = false; }
  else if (hmcSse && !document.hidden && hmcSse.active && !(hmcSse._es && hmcSse._open)) hmcSse.connect();
});
export const hmcSse = new HmcSse("/api/events");
