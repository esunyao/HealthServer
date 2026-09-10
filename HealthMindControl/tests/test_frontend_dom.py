"""hx.js 驱动行为回归：用最小 DOM 桩在 Node 里真实执行驱动逻辑。

覆盖 v0.2 的线上缺陷：容器只有 hx-get + hx-trigger="load"（无 hx-target）时，
必须默认就地渲染响应，而不是丢弃请求让页面停在“载入中…”。
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
JS_DIR = ROOT / "src" / "healthmind_control" / "static" / "js"
HARNESS = Path(__file__).parent / "hx_driver_check.mjs"


def test_hx_driver_renders_without_explicit_target():
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
        proc = subprocess.run([node, "run.mjs"], cwd=workdir, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, f"hx 驱动回归失败：{proc.stdout}\n{proc.stderr}"
        assert "HX-DRIVER-OK" in proc.stdout
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
