// <json-tree> 自定义元素：可折叠 JSON 树（shadow DOM，无依赖，全部 textContent 渲染防注入）
const SENSITIVE_HINT = /token|secret|password|authorization|api[-_]?key|credential|signature/i;

const STYLE = `
  :host { display: block; font-family: var(--mono, monospace); font-size: 12px; line-height: 1.75; color: var(--fg, #dbe6f3); }
  ul { list-style: none; margin: 0; padding-left: 15px; border-left: 1px dashed var(--line-soft, #223); }
  li { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  li.open { white-space: normal; }
  .caret { cursor: pointer; user-select: none; display: inline-block; width: 15px; color: var(--fg-3, #5c7190); }
  .caret:hover { color: var(--accent-strong, #17b5a2); }
  .key { color: var(--accent-strong, #17b5a2); }
  .str { color: #6fce9b; } .num { color: #eab968; } .bool { color: #c4a0f0; }
  .null { color: var(--fg-3, #5c7190); font-style: italic; }
  .meta { color: var(--fg-3, #5c7190); font-size: 11px; margin-left: 4px; }
  .masked { color: var(--err, #ef6b78); font-style: italic; }
`;

class JsonTree extends HTMLElement {
  connectedCallback() {
    if (this._built) return;
    this._built = true;
    const shadow = this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = STYLE;
    shadow.appendChild(style);
    this._host = document.createElement("div");
    shadow.appendChild(this._host);
    this._render();
  }
  static get observedAttributes() { return ["value"]; }
  attributeChangedCallback(name) { if (this._built) this._render(); }
  set value(v) { this._value = v; this.setAttribute("value", ""); if (this._built) this._render(); }
  _render() {
    if (!this._host) return;
    this._host.replaceChildren();
    let value = this._value;
    if (typeof value === "string" && value.trim().startsWith("{")) {
      try { value = JSON.parse(value); } catch { /* 保留原串 */ }
    }
    this._host.appendChild(build(value));
  }
}

function leaf(value) {
  const span = document.createElement("span");
  if (value === null || value === undefined) { span.className = "null"; span.textContent = "null"; }
  else if (typeof value === "string") { span.className = "str"; span.textContent = JSON.stringify(value.length > 400 ? value.slice(0, 400) + "…(" + value.length + ")" : value); }
  else if (typeof value === "number") { span.className = "num"; span.textContent = String(value); }
  else if (typeof value === "boolean") { span.className = "bool"; span.textContent = String(value); }
  else { span.textContent = String(value); }
  span.title = String(value).slice(0, 4000);
  return span;
}

function build(value) {
  const wrap = document.createElement("span");
  if (value === null || typeof value !== "object") { wrap.appendChild(leaf(value)); return wrap; }
  const array = Array.isArray(value);
  const entries = array ? value.map((v, i) => [String(i), v]) : Object.entries(value);
  const ul = document.createElement("ul");
  ul.hidden = false;
  const head = document.createElement("div");
  const caret = document.createElement("span");
  caret.className = "caret";
  caret.textContent = "▼";
  const meta = document.createElement("span");
  meta.className = "meta";
  meta.textContent = (array ? "[" + entries.length + "]" : "{" + entries.length + "}");
  head.append(caret, meta);
  const setOpen = (open) => { ul.hidden = !open; caret.textContent = open ? "▼" : "▶"; };
  caret.addEventListener("click", () => setOpen(ul.hidden));
  wrap.append(head, ul);
  for (const [key, raw] of entries) {
    const li = document.createElement("li");
    const row = document.createElement("div");
    row.style.display = "flex";
    const keyEl = document.createElement("span");
    keyEl.className = "key";
    keyEl.textContent = key + (array ? ":" : ":");
    keyEl.style.flex = "none";
    row.appendChild(keyEl);
    const isContainer = raw !== null && typeof raw === "object";
    const sensitive = !array && SENSITIVE_HINT.test(key) && typeof raw === "string";
    if (sensitive) {
      const masked = document.createElement("span");
      masked.className = "masked";
      masked.textContent = "***（敏感键，服务器已掩码或本端隐藏）";
      row.appendChild(masked);
      li.appendChild(row);
    } else if (isContainer) {
      const sub = build(raw);
      sub.style.display = "none";
      const box = document.createElement("span");
      box.style.flex = "1";
      box.appendChild(sub);
      row.appendChild(box);
      row.style.cursor = "pointer";
      row.addEventListener("click", () => {
        const show = sub.style.display === "none";
        sub.style.display = show ? "" : "none";
        li.classList.toggle("open", show);
        caret.textContent = show ? "▼" : "▶"; // 不影响子树自身 caret
      });
      li.appendChild(row);
    } else {
      row.appendChild(leaf(raw));
      li.appendChild(row);
    }
    ul.appendChild(li);
  }
  return wrap;
}

customElements.define("json-tree", JsonTree);

export function renderJsonTreeEl(value) {
  const el = document.createElement("json-tree");
  el.value = value;
  return el;
}
