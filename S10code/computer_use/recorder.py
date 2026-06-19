"""Session 10: per-step trajectory recorder — the assignment's evidence.

Mirrors the browser skill's per-turn artifact convention (one png + one
json per step, plus a roll-up trajectory.json). No clock dependency: run
folders are numbered by counting existing siblings so tests are
deterministic."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


class TrajectoryRecorder:
    def __init__(self, task: str, run_dir: Path):
        self.task = task
        self.dir = run_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._steps: list[dict] = []
        self._notes: list[str] = []
        self.vision_calls = 0

    def step(self, layer: str, action: str, target: str = "",
             outcome: str = "ok", *, screen_png: bytes | None = None,
             marked_png: bytes | None = None, vision_called: bool = False) -> int:
        n = len(self._steps) + 1
        if vision_called:
            self.vision_calls += 1
        rec = {"n": n, "layer": layer, "action": action, "target": target,
               "outcome": outcome, "vision_called": vision_called}
        if screen_png is not None:
            (self.dir / f"step_{n:02d}_screen.png").write_bytes(screen_png)
            rec["screen"] = f"step_{n:02d}_screen.png"
        if marked_png is not None:
            (self.dir / f"step_{n:02d}_marked.png").write_bytes(marked_png)
            rec["marked"] = f"step_{n:02d}_marked.png"
        (self.dir / f"step_{n:02d}.json").write_text(json.dumps(rec, indent=2))
        self._steps.append(rec)
        return n

    def note(self, message: str) -> None:
        self._notes.append(message)

    def stop(self, result: str | None = None) -> dict:
        traj = {
            "task": self.task,
            "dir": str(self.dir),
            "steps": self._steps,
            "notes": self._notes,
            "layer_counts": dict(Counter(s["layer"] for s in self._steps)),
            "vision_calls": self.vision_calls,
            "result": result,
        }
        (self.dir / "trajectory.json").write_text(json.dumps(traj, indent=2))
        return traj


def start_recording(task: str, root: str | Path) -> TrajectoryRecorder:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    n = sum(1 for p in root.glob(f"{task}_*") if p.is_dir()) + 1
    return TrajectoryRecorder(task, root / f"{task}_{n}")
