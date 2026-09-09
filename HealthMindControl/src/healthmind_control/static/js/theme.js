// theme.js：主题切换（基色 + 强调色 + 跟随系统），localStorage 持久化
const KEY = "hmc.theme";
const BASES = [
  { id: "midnight", label: "深空（默认）", css: "linear-gradient(135deg,#0d1726 0%,#101b2c 55%,#15243a 100%)" },
  { id: "light", label: "明亮", css: "linear-gradient(135deg,#f4f6fa 0%,#ffffff 60%,#e3eaf2 100%)" },
  { id: "slate", label: "石板", css: "linear-gradient(135deg,#171b26 0%,#1d2230 55%,#262d40 100%)" },
  { id: "olive", label: "橄榄护眼", css: "linear-gradient(135deg,#141a11 0%,#1a2217 55%,#233020 100%)" },
];
const ACCENTS = [
  { id: "teal", c: "#2dd4bf" }, { id: "blue", c: "#60a5fa" }, { id: "violet", c: "#a78bfa" },
  { id: "amber", c: "#fbbf24" }, { id: "rose", c: "#fb7185" }, { id: "green", c: "#4ade80" },
];
const VALID_BASES = BASES.map((b) => b.id);
const VALID_ACCENTS = ACCENTS.map((a) => a.id);

export function readTheme() {
  try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; }
}
function persist(theme) {
  try { localStorage.setItem(KEY, JSON.stringify(theme)); } catch { /* ignore */ }
}
export function apply(theme) {
  const sysDark = matchMedia("(prefers-color-scheme: dark)").matches;
  let base = theme.base || "midnight";
  if (theme.system === "auto") base = sysDark ? "midnight" : "light";
  if (!VALID_BASES.includes(base)) base = "midnight";
  const accent = VALID_ACCENTS.includes(theme.accent) ? theme.accent : "teal";
  document.documentElement.dataset.theme = base;
  document.documentElement.dataset.accent = accent;
  return { ...theme, base, accent, resolvedBase: base };
}

function ensureDialog() {
  const dialog = document.getElementById("theme-dialog");
  if (!dialog || dialog.dataset.bound) return dialog;
  dialog.dataset.bound = "1";
  const baseBox = document.getElementById("theme-base-options");
  const accentBox = document.getElementById("theme-accent-options");
  const follow = document.getElementById("theme-follow");

  BASES.forEach((b) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "base-sw";
    const chip = document.createElement("span");
    chip.className = "base-chip";
    chip.style.background = b.css;
    const label = document.createElement("span");
    label.textContent = b.label;
    item.append(chip, label);
    item.dataset.base = b.id;
    item.addEventListener("click", () => {
      const t = readTheme(); t.base = b.id; t.system = "";
      follow.checked = false;
      persist(t); apply(t); paint();
    });
    baseBox.appendChild(item);
  });
  ACCENTS.forEach((a) => {
    const sw = document.createElement("button");
    sw.type = "button";
    sw.className = "sw";
    sw.title = a.id;
    sw.style.background = a.c;
    sw.addEventListener("click", () => {
      const t = readTheme(); t.accent = a.id;
      persist(t); apply(t); paint();
    });
    accentBox.appendChild(sw);
  });
  follow.addEventListener("change", () => {
    const t = readTheme(); t.system = follow.checked ? "auto" : "";
    persist(t); apply(t); paint();
  });
  document.getElementById("theme-done").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => { dialog.style.display = ""; });
  return dialog;
}
function paint() {
  const t = readTheme();
  const resolved = apply(t);
  document.querySelectorAll("#theme-base-options .base-sw").forEach((el) => {
    el.setAttribute("aria-pressed", String(t.system !== "auto" && el.dataset.base === resolved.base));
  });
  document.querySelectorAll("#theme-accent-options .sw").forEach((el) => {
    el.setAttribute("aria-pressed", String(el.title === resolved.accent));
  });
  document.getElementById("theme-follow").checked = t.system === "auto";
}
function init() {
  const theme = readTheme();
  apply(theme);
  document.getElementById("theme-btn").addEventListener("click", () => {
    const dialog = ensureDialog();
    paint();
    if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", "");
  });
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();
