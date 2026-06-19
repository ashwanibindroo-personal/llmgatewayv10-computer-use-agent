"""replay_viewer renders all 8 assignment items into one self-contained HTML."""
import base64
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import persistence
import replay_viewer

# 1x1 red PNG
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _write_session(root: Path, sid: str) -> None:
    d = root / sid
    (d / "nodes").mkdir(parents=True)
    (d / "query.txt").write_text("compare top 3 HF models", encoding="utf-8")
    (d / "graph.json").write_text(json.dumps({
        "directed": True, "multigraph": False, "graph": {},
        "nodes": [{"id": "n:1"}, {"id": "n:2"}],
        "edges": [{"source": "n:1", "target": "n:2"}],
    }), encoding="utf-8")
    (d / "nodes" / "n_001.json").write_text(json.dumps({
        "node_id": "n:1", "skill": "browser", "status": "complete",
        "inputs": [], "prompt_sent": "p1", "retries": 0,
        "result": {"success": True, "agent_name": "browser",
                   "output": {"url": "https://huggingface.co/models",
                              "goal": "filter and sort", "path": "a11y",
                              "turns": 4,
                              "content": "RAW-EXTRACTED-MODEL-LIST",
                              "actions": [{"turn": 1,
                                           "actions": [{"kind": "click", "target": "Sort"}],
                                           "outcome": "ok"}],
                              "final_url": "https://huggingface.co/models?sort=downloads"},
                   "successors": [], "cost": 0.0, "elapsed_s": 3.2,
                   "provider": "gemini", "error": None, "error_code": None},
    }), encoding="utf-8")
    (d / "nodes" / "n_002.json").write_text(json.dumps({
        "node_id": "n:2", "skill": "formatter", "status": "complete",
        "inputs": ["n:1"], "prompt_sent": "p2", "retries": 0,
        "result": {"success": True, "agent_name": "formatter",
                   "output": {"final_answer": "| model | downloads |\n|---|---|"},
                   "successors": [], "cost": 0.0, "elapsed_s": 1.0,
                   "provider": "anthropic", "error": None, "error_code": None},
    }), encoding="utf-8")
    ev = d / "browser" / "browser_123" / "a11y"
    ev.mkdir(parents=True)
    (ev / "turn_01_raw.png").write_bytes(_PNG)
    (ev / "turn_01_legend.txt").write_text("[1]<button>Sort</button>", encoding="utf-8")


def test_renders_all_eight_items(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "SESSIONS_ROOT", tmp_path)
    monkeypatch.setattr(replay_viewer, "SESSIONS_ROOT", tmp_path)
    _write_session(tmp_path, "s1")
    html = replay_viewer.render_session("s1", gateway_url="http://localhost:1")  # port 1 → offline
    assert "compare top 3 HF models" in html                  # 1 goal
    assert "n:1" in html and "n:2" in html and "&rarr;" in html  # 2 DAG nodes+edge
    assert "a11y" in html                                     # 3 cascade layer badge
    assert "click" in html and "Sort" in html                 # 4 exact actions
    assert "base64," in html and "&lt;button&gt;" in html     # 5 evidence (img + legend, escaped)
    assert "RAW-EXTRACTED-MODEL-LIST" in html                 # 6 raw data
    assert "| model | downloads |" in html                    # 7 final table
    assert "turns" in html.lower() and "gateway offline" in html.lower()  # 8 turns + cost fallback


def test_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "SESSIONS_ROOT", tmp_path)
    monkeypatch.setattr(replay_viewer, "SESSIONS_ROOT", tmp_path)
    _write_session(tmp_path, "s2")
    out = replay_viewer.write_report("s2", gateway_url="http://localhost:1")
    assert out.exists() and out.name == "replay.html"
