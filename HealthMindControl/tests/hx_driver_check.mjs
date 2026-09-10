// 最小的 DOM 桩 + hx.js 行为回归校验（Node 执行，无浏览器依赖）
// 断言：容器只有 hx-get/hx-trigger="load" 且没有 hx-target 时，也必须把响应渲染回容器自身。
let alerts = 0;
const fetched = [];

class FakeEvent {
  constructor(type) { this.type = type; this.defaultPrevented = false; }
  preventDefault() { this.defaultPrevented = true; }
}

class FakeEl {
  constructor(tag) {
    this.tagName = tag; this.attrs = {}; this.dataset = {}; this.children = [];
    this._html = ""; this.listeners = {}; this.disabled = false; this.hidden = false;
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  addEventListener(type, cb) { (this.listeners[type] = this.listeners[type] || []).push(cb); }
  closest() { return this; }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  set innerHTML(v) { this._html = v; }
  get innerHTML() { return this._html; }
  replaceChildren() { this._html = ""; }
  appendChild(child) { this.children.push(child); }
  replaceWith() {}
  get firstElementChild() { return null; }
}

class FakeDoc {
  constructor() { this.readyState = "complete"; this.elements = []; this.byId = new Map(); this.body = {}; }
  querySelectorAll(sel) {
    if (sel === "[hx-get]") return this.elements.filter((e) => e.getAttribute("hx-get") !== null);
    return [];
  }
  querySelector(sel) { return this.byId.get(sel) || null; }
  getElementById(id) { return this.byId.get("#" + id) || null; }
  addEventListener() {}
  createElement(tag) { return new FakeEl(tag); }
}

function setGlobal(name, value) {
  try { globalThis[name] = value; }
  catch { Object.defineProperty(globalThis, name, { value, configurable: true, writable: true }); }
}

const doc = new FakeDoc();
setGlobal("document", doc);
setGlobal("window", {
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent() {},
  location: { search: "" },
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  requestAnimationFrame: (cb) => cb(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (id) => clearTimeout(id),
  navigator: { clipboard: { writeText: async () => {} } },
});
if (typeof globalThis.CustomEvent !== "function") {
  setGlobal("CustomEvent", class { constructor(type, opts) { this.type = type; Object.assign(this, opts || {}); } });
}
setGlobal("MutationObserver", class { observe() {} disconnect() {} });
setGlobal("customElements", { define() {} });
setGlobal("navigator", { clipboard: { writeText: async () => {} } });
setGlobal("history", { pushState() {} });
setGlobal("alert", () => { alerts += 1; });
// json-tree.js 在模块加载时继承 HTMLElement（此处只需可被继承的基类）
setGlobal("HTMLElement", class {});

// 过滤器表单：一个 status=failed 的输入
const form = new FakeEl("form");
const input = new FakeEl("input");
input.name = "status"; input.value = "failed"; input.type = "text"; input.disabled = false;
form.addEventListener = form.addEventListener.bind(form);
form.querySelectorAll = () => [input];
doc.byId.set("#tasks-filters", form);

// 容器：只有 hx-get + hx-include + hx-trigger="load"，故意不给 hx-target
const container = new FakeEl("div");
container.setAttribute("hx-get", "/ui/parts/tasks");
container.setAttribute("hx-include", "#tasks-filters");
container.setAttribute("hx-trigger", "load");
doc.elements.push(container);

globalThis.fetch = async (url) => {
  fetched.push(String(url));
  return { ok: true, status: 200, text: async () => '<div class="tbl">ROWS-OK</div>', json: async () => ({}) };
};

await import("./js/hx.js");
await new Promise((resolve) => setTimeout(resolve, 80));

const failures = [];
if (fetched.length !== 1) failures.push("期望发起 1 次请求，实际 " + fetched.length);
if (fetched[0] && !fetched[0].includes("status=failed")) failures.push("请求未携带 hx-include 过滤参数: " + fetched[0]);
if (!container.innerHTML.includes("ROWS-OK")) failures.push("容器未使用默认 target 渲染响应（回归：hx-target 缺失导致停在载入中）");
if (alerts !== 0) failures.push("出现告警提示 " + alerts + " 次（不应有）");

if (failures.length) {
  console.error("HX-DRIVER-FAIL: " + failures.join(" | "));
  process.exit(1);
}
console.log("HX-DRIVER-OK url=" + fetched[0]);
