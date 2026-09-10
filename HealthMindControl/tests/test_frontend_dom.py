"""前端驱动回归：hx.js 行为 + SSE 全站加载。

用最小 DOM 桩在 Node 里真实执行驱动逻辑（无浏览器依赖），覆盖两个真实缺陷：
1. 容器只有 hx-get + hx-trigger="load"（无 hx-target）时必须默认就地渲染，
   否则页面停在“载入中…”；
2. sse.js 必须在任意页面都自动建立单一连接并更新页脚状态，否则非总览页
   会一直显示“SSE 连接中…”。
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
JS_DIR = ROOT / "src" / "healthmind_control" / "static" / "js"
HARNESS = Path(__file__).parent / "hx_driver_check.mjs"
BASE_TEMPLATE = ROOT / "src" / "healthmind_control" / "templates" / "base.html"


def test_frontend_drivers_behave_in_dom_harness():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    workdir = ROOT / "var" / "tmp-hx-dom"
    shutil.rmtree(workdir, ignore_errors=True)
    (workdir / "js").mkdir(parents=True, exist_ok=True)
    # .js + package.json type=module，使 Node 以 ESM 方式加载驱动
    (workdir / "package.json").write_text(json.dumps({"type": "module"}), encoding="utf-8")
    for source in JS_DIR.rglob("*.js"):
        target = workdir / "js" / source.relative_to(JS_DIR)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    (workdir / "run.mjs").write_bytes(HARNESS.read_bytes())
    try:
        proc = subprocess.run(
            [node, "run.mjs"], cwd=workdir, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        assert proc.returncode == 0, f"前端驱动回归失败：{proc.stdout}\n{proc.stderr}"
        assert "HX-DRIVER-OK" in proc.stdout
        assert "SSE-DRIVER-OK" in proc.stdout
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_base_template_loads_core_modules_on_every_page():
    """回归：SSE 模块必须在 base 模板全站加载。

    之前 sse.js 只被 dashboard.js 引入，导致总览页之外的所有页面页脚一直显示
    “SSE 连接中…”（真实缺陷）。
    """
    html = BASE_TEMPLATE.read_text(encoding="utf-8")
    for module in ("theme.js", "hx.js", "main.js", "sse.js"):
        assert f"/static/js/{module}" in html, f"base.html 缺少全站模块 {module}"
