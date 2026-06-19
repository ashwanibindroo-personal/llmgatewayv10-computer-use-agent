import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from computer_use.recorder import start_recording


def test_records_steps_and_flushes_trajectory(tmp_path):
    rec = start_recording("calculator", tmp_path)
    assert rec.dir.exists()
    rec.step("hotkeys", "type", "12.5*8+100", outcome="ok")
    rec.note("tried hotkeys → ok")
    rec.step("hotkeys", "read_clipboard", outcome="1100")
    traj = rec.stop(result="1100")

    assert traj["vision_calls"] == 0
    assert traj["layer_counts"] == {"hotkeys": 2}
    assert traj["result"] == "1100"
    on_disk = json.loads((rec.dir / "trajectory.json").read_text())
    assert on_disk["task"] == "calculator"
    assert len(list(rec.dir.glob("step_*.json"))) == 2


def test_counts_vision_calls_and_writes_pngs(tmp_path):
    rec = start_recording("paint", tmp_path)
    rec.step("vision", "click", "red circle target",
             screen_png=b"\x89PNG_raw", marked_png=b"\x89PNG_marked",
             vision_called=True)
    traj = rec.stop()
    assert traj["vision_calls"] == 1
    assert (rec.dir / "step_01_screen.png").read_bytes() == b"\x89PNG_raw"
    assert (rec.dir / "step_01_marked.png").read_bytes() == b"\x89PNG_marked"


def test_sibling_runs_get_distinct_dirs(tmp_path):
    a = start_recording("calculator", tmp_path)
    b = start_recording("calculator", tmp_path)
    assert a.dir != b.dir
