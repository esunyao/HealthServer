"""守护第①段纯图：不依赖任何模型、API Key 或网络。"""

import json
from pathlib import Path

from nutriathena_agent.basic_graph import build_graph, graph


def test_langgraph_dev_config_points_to_compiled_graph():
    config = json.loads((Path(__file__).resolve().parents[1] / "langgraph.json").read_text(encoding="utf-8"))
    assert config["graphs"] == {"basic_graph": "./src/nutriathena_agent/basic_graph.py:graph"}
    assert graph.invoke({"text": "午饭吃了番茄炒蛋", "notes": []})["route"] == "accept"


def test_long_text_goes_to_accept():
    result = build_graph().invoke({"text": "午饭吃了番茄炒蛋和米饭", "notes": []})
    assert result["route"] == "accept"


def test_short_text_goes_to_reject():
    result = build_graph().invoke({"text": "嗯", "notes": []})
    assert result["route"] == "reject"


def test_text_is_normalized():
    result = build_graph().invoke({"text": "  午饭  ", "notes": []})
    assert result["text"] == "午饭"


def test_boundary_length_counts_as_accept():
    """长度判定是 >= MIN_LENGTH，边界值应落在 accept。"""
    result = build_graph().invoke({"text": "12345", "notes": []})
    assert result["route"] == "accept"


def test_notes_reducer_accumulates():
    """有 reducer 时 notes 会累加三个节点的追加，而不是被最后一个覆盖。"""
    result = build_graph().invoke({"text": "午饭吃了番茄炒蛋", "notes": []})
    assert len(result["notes"]) == 3
    assert result["notes"][0].startswith("normalize:")
    assert result["notes"][1].startswith("judge:")
    assert result["notes"][2].startswith("accept:")
