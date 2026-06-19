# Session 10 Computer-Use Agent Implementation Plan

> ⚠️ **Historical implementation plan — partially superseded.** Kept for process
> history. The plan targeted **VS Code** for the Electron task and **MS Paint**
> for the vision task; during live testing on Windows 11 both were re-targeted —
> to a bundled minimal Electron app and a label-less HTML canvas with
> **set-of-marks**, respectively (VS Code doesn't expose its renderer to CDP;
> pyautogui can't draw in Win11 Paint and raw-coordinate vision is too imprecise).
> The task identifiers `vscode`/`paint` became `electron`/`canvas`. For the
> current, authoritative description see [`README.md`](../../../README.md) and
> [`ARCHITECTURE.md`](../../../ARCHITECTURE.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `computer_use` skill to the Session 9 DAG skill catalog (in a self-contained Session 10 repo) that automates the local Windows machine through a cost-laddered cascade and completes three tasks (Calculator, VS Code via Electron debug port, MS Paint via vision).

**Architecture:** The skill plugs into the frozen Session 8/9 orchestrator exactly like `browser` — a YAML catalog block + prompt + one dispatch branch in `skills.py` that hands a `NodeSpec` to `ComputerUseSkill.run()` and returns an `AgentResult`. `ComputerUseSkill` owns a cascade (hotkeys → AX-tree → AX+text-LLM → Electron-CDP → vision), escalating only on insufficiency, and records a per-step trajectory.

**Tech Stack:** Python 3.11+, `uv`, Pydantic, `pyautogui`, `pyperclip`, `pywinauto` (UIAutomation), `playwright` (CDP), `mss`/`Pillow`, the reused Session 9 `llm_gatewayV9` (Anthropic) via `browser/client.py`'s `V9Client`, `pytest`.

## Global Constraints

- **Platform:** Windows 11 only. Controllers may use Windows-only APIs (UIAutomation, `pyautogui`). No cross-platform branch.
- **Frozen orchestrator:** `flow.py` MUST stay byte-identical to the Session 9 copy. Capability is added via data (YAML + prompt) + the one `skills.py` dispatch branch only — same invariant `browser` honored.
- **Cascade discipline:** every layer escalates ONLY when it cannot locate/act on the needed control or returns empty. Each escalation is logged into the trajectory as `tried <layer> → insufficient (<reason>) → escalating to <layer>`.
- **Constraint coverage (must hold):** Calculator = **zero vision calls** (`vision_calls == 0`); VS Code = **Electron debug-port** path; MS Paint = **vision (Layer 3)**.
- **Reuse, don't duplicate:** import `V9Client` from `browser/client.py`; do not copy it.
- **No new gateway providers/routing changes.**
- **Commit after every task.** Tests via `uv run pytest`. Work inside `S10code/`.
- **Layer name vocabulary (use verbatim everywhere):** `"hotkeys"`, `"ax"`, `"ax_llm"`, `"electron"`, `"vision"`.

---

### Task 1: Scaffold the self-contained Session 10 repo

**Files:**
- Create: `S10code/` (copied tree from `Session 9/S9code`)
- Create: `llm_gatewayV9/` (copied tree from `Session 9/llm_gatewayV9`)
- Modify: `S10code/requirements.txt`, `S10code/pyproject.toml`
- Create: `.gitignore` (repo root)

**Interfaces:**
- Produces: a Session 10 repo where `cd S10code && uv run python -c "import schemas, skills, flow"` succeeds, and `pyautogui`, `pyperclip`, `pywinauto`, `mss` are installed.

- [ ] **Step 1: Copy the Session 9 code and gateway into Session 10**

```bash
cd "/c/The School Of AI/Session 10 - Computer Use Agent"
SRC="/c/The School Of AI/Session 9 - Browser Agents & Autonomous Web"
# Copy code tree, excluding venvs, caches, and prior session state/traces.
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' \
  --exclude='state/sessions' --exclude='state/index.faiss' --exclude='state/index_ids.json' \
  "$SRC/S9code/" ./S10code/
rsync -a --exclude='.venv' --exclude='__pycache__' "$SRC/llm_gatewayV9/" ./llm_gatewayV9/
# Preserve the empty sessions dir so the recorder has a root.
mkdir -p ./S10code/state/sessions
```

- [ ] **Step 2: Add the new dependencies**

Append to `S10code/requirements.txt`:

```
pyautogui
pyperclip
pywinauto
mss
```

And add the same four to the `dependencies` list in `S10code/pyproject.toml` (match the existing list's formatting).

- [ ] **Step 3: Sync and install Playwright Chromium (already used by browser skill)**

Run:
```bash
cd "/c/The School Of AI/Session 10 - Computer Use Agent/S10code" && uv sync
```
Expected: resolves and installs including the four new packages, exit 0.

- [ ] **Step 4: Verify imports**

Run:
```bash
cd "/c/The School Of AI/Session 10 - Computer Use Agent/S10code" && uv run python -c "import schemas, skills, flow, pyautogui, pyperclip, pywinauto, mss; print('OK')"
```
Expected: `OK` (a single line; pyautogui may emit a one-time mouse-info warning — acceptable).

- [ ] **Step 5: Write the repo .gitignore**

Create `/.gitignore` at repo root:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
S10code/state/sessions/
*.mp4
.env
```

- [ ] **Step 6: Commit**

```bash
cd "/c/The School Of AI/Session 10 - Computer Use Agent"
git add S10code llm_gatewayV9 .gitignore
git commit -m "chore: scaffold self-contained Session 10 repo from S9 + computer-use deps"
```

---

### Task 2: `ComputerUseOutput` schema

**Files:**
- Modify: `S10code/schemas.py` (add model after `BrowserOutput`, ~line 156; add one `ErrorCode` member)
- Test: `S10code/tests/test_computer_use_schema.py`

**Interfaces:**
- Produces: `ComputerUseOutput(task: str, path: Literal["hotkeys","ax","ax_llm","electron","vision"], turns: int=0, result: str|None=None, actions: list[dict]=[], trajectory_dir: str|None=None, vision_calls: int=0)` and a new `ErrorCode` member `"controller_unavailable"`.

- [ ] **Step 1: Write the failing test**

```python
# S10code/tests/test_computer_use_schema.py
from schemas import ComputerUseOutput


def test_computer_use_output_roundtrip():
    out = ComputerUseOutput(
        task="calculator", path="hotkeys", turns=3, result="1100",
        actions=[{"layer": "hotkeys", "keys": "12.5*8+100"}],
        trajectory_dir="state/sessions/s/computer_use/calculator_1",
        vision_calls=0,
    )
    d = out.model_dump()
    assert d["task"] == "calculator"
    assert d["path"] == "hotkeys"
    assert d["vision_calls"] == 0
    assert ComputerUseOutput.model_validate(d).result == "1100"


def test_path_must_be_known_layer():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ComputerUseOutput(task="x", path="telepathy")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd S10code && uv run pytest tests/test_computer_use_schema.py -v`
Expected: FAIL with `ImportError: cannot import name 'ComputerUseOutput'`.

- [ ] **Step 3: Add the schema**

In `S10code/schemas.py`, immediately after the `BrowserOutput` class add:

```python
class ComputerUseOutput(BaseModel):
    """Session 10: typed payload the ComputerUse skill writes into
    AgentResult.output. `path` is the cascade layer the skill settled on;
    `vision_calls` lets the zero-vision constraint be asserted from the
    output alone."""

    task: str
    path: Literal["hotkeys", "ax", "ax_llm", "electron", "vision"]
    turns: int = 0
    result: str | None = None
    actions: list[dict] = Field(default_factory=list)
    trajectory_dir: str | None = None
    vision_calls: int = 0
```

And add `"controller_unavailable"` as a new member of the `ErrorCode` `Literal` (with a trailing comment `# a required OS controller/app was unavailable`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd S10code && uv run pytest tests/test_computer_use_schema.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add S10code/schemas.py S10code/tests/test_computer_use_schema.py
git commit -m "feat: add ComputerUseOutput schema + controller_unavailable error code"
```

---

### Task 3: `TrajectoryRecorder` (`start_recording`)

**Files:**
- Create: `S10code/computer_use/__init__.py`
- Create: `S10code/computer_use/recorder.py`
- Test: `S10code/tests/test_recorder.py`

**Interfaces:**
- Produces:
  - `start_recording(task: str, root: str | Path) -> TrajectoryRecorder` — creates `<root>/<task>_<n>/` (n = count of existing siblings + 1; deterministic, no clock dependency in tests).
  - `TrajectoryRecorder.step(layer: str, action: str, target: str = "", outcome: str = "ok", *, screen_png: bytes | None = None, marked_png: bytes | None = None, vision_called: bool = False) -> int` — writes `step_NN.json` (+ pngs when given), returns the step number.
  - `TrajectoryRecorder.note(message: str) -> None` — appends an escalation/info line to the in-memory log.
  - `TrajectoryRecorder.stop(result: str | None = None) -> dict` — writes `trajectory.json` (`{task, dir, steps:[...], notes:[...], layer_counts:{...}, vision_calls:int, result}`) and returns it.
  - `TrajectoryRecorder.dir -> Path`, `.vision_calls -> int`.

- [ ] **Step 1: Write the failing test**

```python
# S10code/tests/test_recorder.py
import json
from pathlib import Path
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd S10code && uv run pytest tests/test_recorder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'computer_use'`.

- [ ] **Step 3: Implement the recorder**

Create `S10code/computer_use/__init__.py` (empty file).

Create `S10code/computer_use/recorder.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd S10code && uv run pytest tests/test_recorder.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add S10code/computer_use/__init__.py S10code/computer_use/recorder.py S10code/tests/test_recorder.py
git commit -m "feat: add TrajectoryRecorder (start_recording) for computer-use evidence"
```

---

### Task 4: Pure controller helpers (testable logic)

**Files:**
- Create: `S10code/computer_use/controllers.py`
- Test: `S10code/tests/test_controllers_pure.py`

**Interfaces:**
- Produces (pure, unit-tested):
  - `build_calculator_keys(expression: str) -> list[str]` — maps an arithmetic expression to a pyautogui key token list (digits/`.` as themselves; `+ - * /` → `add subtract multiply divide`; `=` → `enter`). Raises `ValueError` on an unsupported char.
  - `serialize_ax_legend(controls: list[dict]) -> tuple[str, dict[int, dict]]` — numbers a list of `{name, control_type, value?}` dicts into a legend string (`[1] Button "Seven"` ...) and an index→control map.
  - `parse_action(text: str) -> dict` — parses a single JSON action object out of LLM text (strips ``` fences; falls back to first `{...}`).
- Produces (live wrappers, NOT unit-tested — exercised in Task 9 smoke): `LiveDesktop` class with `focus_window(title_re)`, `type_keys(tokens)`, `read_clipboard()`, `screenshot() -> bytes`, `click(x, y)`, `drag(path)`, `ax_controls(title_re) -> list[dict]`, `invoke_control(title_re, name)`.

- [ ] **Step 1: Write the failing test**

```python
# S10code/tests/test_controllers_pure.py
import pytest
from computer_use.controllers import (
    build_calculator_keys, serialize_ax_legend, parse_action,
)


def test_build_calculator_keys_basic():
    assert build_calculator_keys("12.5*8+100=") == [
        "1", "2", ".", "5", "multiply", "8", "add", "1", "0", "0", "enter",
    ]


def test_build_calculator_keys_rejects_unknown_char():
    with pytest.raises(ValueError):
        build_calculator_keys("2^3")


def test_serialize_ax_legend_numbers_controls():
    legend, idx = serialize_ax_legend([
        {"name": "Seven", "control_type": "Button"},
        {"name": "Plus", "control_type": "Button", "value": "+"},
    ])
    assert "[1] Button \"Seven\"" in legend
    assert "[2] Button \"Plus\"" in legend
    assert idx[2]["name"] == "Plus"


def test_parse_action_strips_fences():
    assert parse_action('```json\n{"action": "click", "mark": 3}\n```') == {
        "action": "click", "mark": 3,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd S10code && uv run pytest tests/test_controllers_pure.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'computer_use.controllers'`.

- [ ] **Step 3: Implement controllers (pure helpers + live wrappers)**

Create `S10code/computer_use/controllers.py`:

```python
"""Session 10: Windows OS controllers for the computer-use cascade.

Two halves:
  * Pure helpers (key-token building, AX-legend serialisation, action
    parsing) — deterministic, unit-tested, no machine access.
  * LiveDesktop — thin wrappers over pyautogui / pywinauto / mss that
    actually drive the machine. Not unit-tested (they move the real
    mouse/keyboard); exercised by the Task 9 live smoke runner.
"""
from __future__ import annotations

import json
import re
import time

_OP_TOKENS = {"+": "add", "-": "subtract", "*": "multiply", "/": "divide", "=": "enter"}


def build_calculator_keys(expression: str) -> list[str]:
    """Map an arithmetic expression to pyautogui key tokens for Windows
    Calculator. Digits and '.' map to themselves; operators map to the
    calc app's named keys. Unsupported characters raise ValueError so a
    bad expression fails loudly instead of typing garbage."""
    tokens: list[str] = []
    for ch in expression.replace(" ", ""):
        if ch.isdigit() or ch == ".":
            tokens.append(ch)
        elif ch in _OP_TOKENS:
            tokens.append(_OP_TOKENS[ch])
        else:
            raise ValueError(f"unsupported character in expression: {ch!r}")
    return tokens


def serialize_ax_legend(controls: list[dict]) -> tuple[str, dict[int, dict]]:
    """Number a flat list of AX controls into a legend string + index map.
    Cheap text the Layer-2b LLM reads instead of an image."""
    lines, idx = [], {}
    for i, c in enumerate(controls, start=1):
        name = c.get("name", "")
        ctype = c.get("control_type", "Control")
        val = c.get("value")
        line = f'[{i}] {ctype} "{name}"'
        if val:
            line += f" = {val!r}"
        lines.append(line)
        idx[i] = c
    return "\n".join(lines), idx


def parse_action(text: str) -> dict:
    """Parse a single JSON action object from LLM text (fence-tolerant)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[:-3]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except json.JSONDecodeError:
                pass
    return {}


class ControllerUnavailable(RuntimeError):
    """A required OS controller or target app could not be reached."""


class LiveDesktop:
    """Thin live wrappers. Imports happen lazily so the pure helpers above
    (and their tests) never require a desktop session."""

    def __init__(self, slowmo_ms: int = 0):
        self.slowmo_ms = slowmo_ms

    def _pause(self):
        if self.slowmo_ms:
            time.sleep(self.slowmo_ms / 1000.0)

    def type_keys(self, tokens: list[str]) -> None:
        import pyautogui
        for tok in tokens:
            pyautogui.press(tok) if len(tok) > 1 or tok.isalpha() else pyautogui.typewrite(tok)
            self._pause()

    def read_clipboard(self) -> str:
        import pyperclip
        return pyperclip.paste()

    def hotkey(self, *keys: str) -> None:
        import pyautogui
        pyautogui.hotkey(*keys)
        self._pause()

    def screenshot(self) -> bytes:
        import io
        import mss
        from PIL import Image
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])
            img = Image.frombytes("RGB", shot.size, shot.rgb)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def click(self, x: int, y: int) -> None:
        import pyautogui
        pyautogui.click(x, y)
        self._pause()

    def drag(self, path: list[tuple[int, int]]) -> None:
        import pyautogui
        if not path:
            return
        pyautogui.moveTo(*path[0])
        pyautogui.mouseDown()
        for x, y in path[1:]:
            pyautogui.moveTo(x, y, duration=0.05)
        pyautogui.mouseUp()
        self._pause()

    def focus_window(self, title_re: str):
        from pywinauto import Desktop
        try:
            win = Desktop(backend="uia").window(title_re=title_re)
            win.set_focus()
            return win
        except Exception as e:  # noqa: BLE001
            raise ControllerUnavailable(f"window {title_re!r}: {e}") from e

    def ax_controls(self, title_re: str) -> list[dict]:
        win = self.focus_window(title_re)
        out = []
        for c in win.descendants():
            try:
                out.append({"name": c.window_text(),
                            "control_type": c.element_info.control_type})
            except Exception:  # noqa: BLE001
                continue
        return out

    def invoke_control(self, title_re: str, name: str) -> bool:
        win = self.focus_window(title_re)
        try:
            win.child_window(title=name, control_type="Button").invoke()
            self._pause()
            return True
        except Exception:  # noqa: BLE001
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd S10code && uv run pytest tests/test_controllers_pure.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add S10code/computer_use/controllers.py S10code/tests/test_controllers_pure.py
git commit -m "feat: add computer-use controllers (pure helpers + live desktop wrappers)"
```

---

### Task 5: Drivers — AX-text + vision loops

**Files:**
- Create: `S10code/computer_use/drivers.py`
- Test: `S10code/tests/test_drivers.py`

**Interfaces:**
- Consumes: `parse_action`, `serialize_ax_legend` (Task 4); `V9Client` (reused from `browser/client.py`) — only its `.chat()`/`.vision()` async methods are called, so tests inject a fake.
- Produces:
  - `DriverConfig(goal: str, max_steps: int = 10, max_failures: int = 3, recorder=None)`.
  - `DriverResult(success: bool, turns: int = 0, result: str | None = None, note: str = "")`.
  - `async AXTextDriver(desktop, client, cfg, title_re).run() -> DriverResult` — loops: read AX legend → `client.chat` → `parse_action` → invoke; stops on `{"action":"done","result":...}` or caps. No vision.
  - `async VisionDriver(desktop, client, cfg).run() -> DriverResult` — loops: screenshot → `client.vision` → `parse_action` → click/drag; records `vision_called=True` each turn; stops on `done` or caps.

- [ ] **Step 1: Write the failing test**

```python
# S10code/tests/test_drivers.py
import asyncio
from computer_use.drivers import AXTextDriver, VisionDriver, DriverConfig


class FakeClient:
    def __init__(self, replies):
        self._replies = list(replies)
        self.chat_calls = 0
        self.vision_calls = 0

    async def chat(self, prompt, **kw):
        self.chat_calls += 1
        return _R(self._replies.pop(0))

    async def vision(self, image_data_url, prompt, **kw):
        self.vision_calls += 1
        return _R(self._replies.pop(0))


class _R:
    def __init__(self, text):
        self.text = text


class FakeDesktop:
    def __init__(self):
        self.invoked = []
        self.clicked = []

    def ax_controls(self, title_re):
        return [{"name": "Seven", "control_type": "Button"}]

    def invoke_control(self, title_re, name):
        self.invoked.append(name)
        return True

    def screenshot(self):
        return b"PNG"

    def click(self, x, y):
        self.clicked.append((x, y))


def test_ax_text_driver_stops_on_done():
    client = FakeClient(['{"action":"invoke","name":"Seven"}',
                         '{"action":"done","result":"7"}'])
    desktop = FakeDesktop()
    cfg = DriverConfig(goal="press seven then done", max_steps=5)
    res = asyncio.run(AXTextDriver(desktop, client, cfg, title_re="Calc").run())
    assert res.success and res.result == "7"
    assert desktop.invoked == ["Seven"]
    assert client.vision_calls == 0


def test_vision_driver_clicks_then_done_and_counts_vision():
    client = FakeClient(['{"action":"click","x":10,"y":20}',
                         '{"action":"done","result":"drawn"}'])
    desktop = FakeDesktop()
    cfg = DriverConfig(goal="click target", max_steps=5)
    res = asyncio.run(VisionDriver(desktop, client, cfg).run())
    assert res.success and res.result == "drawn"
    assert desktop.clicked == [(10, 20)]
    assert client.vision_calls == 2  # one per turn


def test_driver_gives_up_after_max_steps():
    client = FakeClient(['{"action":"invoke","name":"Seven"}'] * 10)
    cfg = DriverConfig(goal="never done", max_steps=3)
    res = asyncio.run(AXTextDriver(FakeDesktop(), client, cfg, title_re="Calc").run())
    assert not res.success
    assert res.turns == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd S10code && uv run pytest tests/test_drivers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'computer_use.drivers'`.

- [ ] **Step 3: Implement the drivers**

Create `S10code/computer_use/drivers.py`:

```python
"""Session 10: bounded per-layer driver loops for the computer-use cascade.

Shape mirrors browser/driver.py: a step loop with a step cap and a
consecutive-failure cap, writing per-turn evidence through the recorder.
AXTextDriver is the cheap interactive layer (text LLM, no image).
VisionDriver is the expensive last resort (one /v1/vision call per turn)."""
from __future__ import annotations

import base64
from dataclasses import dataclass

from .controllers import parse_action, serialize_ax_legend


@dataclass
class DriverConfig:
    goal: str
    max_steps: int = 10
    max_failures: int = 3
    recorder: object | None = None


@dataclass
class DriverResult:
    success: bool
    turns: int = 0
    result: str | None = None
    note: str = ""


_AX_SYS = (
    "You drive a Windows app via its accessibility tree. Each turn you see a "
    "numbered legend of controls and the goal. Reply with ONE JSON action: "
    '{"action":"invoke","name":"<control name>"} to click a control, or '
    '{"action":"done","result":"<answer>"} when the goal is complete. '
    "No prose, JSON only."
)

_VISION_SYS = (
    "You drive a Windows desktop by looking at a screenshot. Each turn reply "
    'with ONE JSON action: {"action":"click","x":<int>,"y":<int>}, '
    '{"action":"drag","path":[[x,y],...]}, or '
    '{"action":"done","result":"<summary>"} when the goal is complete. '
    "Coordinates are absolute screen pixels. JSON only."
)


class AXTextDriver:
    LAYER = "ax_llm"

    def __init__(self, desktop, client, cfg: DriverConfig, title_re: str):
        self.d = desktop
        self.client = client
        self.cfg = cfg
        self.title_re = title_re

    async def run(self) -> DriverResult:
        failures = 0
        for turn in range(1, self.cfg.max_steps + 1):
            controls = self.d.ax_controls(self.title_re)
            legend, idx = serialize_ax_legend(controls)
            prompt = f"GOAL: {self.cfg.goal}\n\nCONTROLS:\n{legend}"
            reply = await self.client.chat(prompt, system=_AX_SYS, max_tokens=300)
            act = parse_action(reply.text)
            if act.get("action") == "done":
                if self.cfg.recorder:
                    self.cfg.recorder.step(self.LAYER, "done",
                                           outcome=str(act.get("result")))
                return DriverResult(True, turn, str(act.get("result")), "done")
            if act.get("action") == "invoke" and act.get("name"):
                ok = self.d.invoke_control(self.title_re, act["name"])
                if self.cfg.recorder:
                    self.cfg.recorder.step(self.LAYER, "invoke", act["name"],
                                           outcome="ok" if ok else "fail")
                failures = 0 if ok else failures + 1
            else:
                failures += 1
            if failures >= self.cfg.max_failures:
                return DriverResult(False, turn, None, "too many failures")
        return DriverResult(False, self.cfg.max_steps, None, "step cap")


class VisionDriver:
    LAYER = "vision"

    def __init__(self, desktop, client, cfg: DriverConfig):
        self.d = desktop
        self.client = client
        self.cfg = cfg

    async def run(self) -> DriverResult:
        failures = 0
        for turn in range(1, self.cfg.max_steps + 1):
            png = self.d.screenshot()
            data_url = "data:image/png;base64," + base64.b64encode(png).decode()
            prompt = f"GOAL: {self.cfg.goal}"
            reply = await self.client.vision(data_url, prompt,
                                             system=_VISION_SYS, max_tokens=300)
            act = parse_action(reply.text)
            action = act.get("action")
            if action == "done":
                if self.cfg.recorder:
                    self.cfg.recorder.step(self.LAYER, "done",
                                           outcome=str(act.get("result")),
                                           screen_png=png, vision_called=True)
                return DriverResult(True, turn, str(act.get("result")), "done")
            if action == "click" and "x" in act and "y" in act:
                self.d.click(int(act["x"]), int(act["y"]))
                if self.cfg.recorder:
                    self.cfg.recorder.step(self.LAYER, "click",
                                           f'{act["x"]},{act["y"]}',
                                           screen_png=png, vision_called=True)
                failures = 0
            elif action == "drag" and act.get("path"):
                self.d.drag([tuple(p) for p in act["path"]])
                if self.cfg.recorder:
                    self.cfg.recorder.step(self.LAYER, "drag",
                                           str(act["path"]),
                                           screen_png=png, vision_called=True)
                failures = 0
            else:
                if self.cfg.recorder:
                    self.cfg.recorder.step(self.LAYER, "noop", outcome="unparsed",
                                           screen_png=png, vision_called=True)
                failures += 1
            if failures >= self.cfg.max_failures:
                return DriverResult(False, turn, None, "too many failures")
        return DriverResult(False, self.cfg.max_steps, None, "step cap")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd S10code && uv run pytest tests/test_drivers.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add S10code/computer_use/drivers.py S10code/tests/test_drivers.py
git commit -m "feat: add AX-text and vision driver loops for computer-use cascade"
```

---

### Task 6: `ComputerUseSkill` cascade + per-task entries

**Files:**
- Create: `S10code/computer_use/skill.py`
- Test: `S10code/tests/test_skill_cascade.py`

**Interfaces:**
- Consumes: `LiveDesktop`/`build_calculator_keys`/`ControllerUnavailable` (Task 4), `AXTextDriver`/`VisionDriver`/`DriverConfig`/`DriverResult` (Task 5), `start_recording` (Task 3), `ComputerUseOutput`/`AgentResult`/`NodeSpec` (schema), `V9Client` (reused).
- Produces: `ComputerUseSkill(gateway_url="http://localhost:8109", artifacts_root: str|None, session: str|None, slowmo_ms: int = 0)` with `async run(node: NodeSpec) -> AgentResult`. Dispatches on `node.metadata["task"]` ∈ {`calculator`, `vscode`, `paint`}. Calculator path sets `vision_calls=0`; paint path uses vision; vscode path uses the Electron CDP layer (`_run_electron`). Each method records steps + escalation notes and packs `ComputerUseOutput`.
- The task methods are written so tests can monkeypatch the layer entrypoints (`_calc_hotkeys`, `_run_ax_llm`, `_run_vision`, `_run_electron`) to avoid touching the machine.

- [ ] **Step 1: Write the failing test**

```python
# S10code/tests/test_skill_cascade.py
import asyncio
from pathlib import Path
from computer_use.skill import ComputerUseSkill
from computer_use.drivers import DriverResult
from schemas import NodeSpec


def _skill(tmp_path):
    return ComputerUseSkill(artifacts_root=str(tmp_path), session="t")


def test_calculator_uses_hotkeys_zero_vision(tmp_path, monkeypatch):
    sk = _skill(tmp_path)
    monkeypatch.setattr(sk, "_calc_hotkeys", lambda goal, expr, rec: "1100")
    node = NodeSpec(skill="computer_use",
                    metadata={"task": "calculator", "expression": "12.5*8+100="})
    res = asyncio.run(sk.run(node))
    assert res.success
    assert res.output["path"] == "hotkeys"
    assert res.output["result"] == "1100"
    assert res.output["vision_calls"] == 0


def test_paint_uses_vision_path(tmp_path, monkeypatch):
    sk = _skill(tmp_path)
    async def fake_vision(goal, rec):
        rec.step("vision", "click", "target", vision_called=True)
        return DriverResult(True, 2, "drawn")
    monkeypatch.setattr(sk, "_run_vision", fake_vision)
    node = NodeSpec(skill="computer_use", metadata={"task": "paint"})
    res = asyncio.run(sk.run(node))
    assert res.success and res.output["path"] == "vision"
    assert res.output["vision_calls"] == 1


def test_vscode_uses_electron_path(tmp_path, monkeypatch):
    sk = _skill(tmp_path)
    async def fake_electron(goal, meta, rec):
        rec.step("electron", "create_file", "scratch.txt")
        return DriverResult(True, 1, "saved")
    monkeypatch.setattr(sk, "_run_electron", fake_electron)
    node = NodeSpec(skill="computer_use",
                    metadata={"task": "vscode", "content": "hello"})
    res = asyncio.run(sk.run(node))
    assert res.success and res.output["path"] == "electron"
    assert res.output["vision_calls"] == 0


def test_unknown_task_fails_cleanly(tmp_path):
    sk = _skill(tmp_path)
    res = asyncio.run(sk.run(NodeSpec(skill="computer_use", metadata={"task": "fly"})))
    assert not res.success and res.error_code == "interaction_failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd S10code && uv run pytest tests/test_skill_cascade.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'computer_use.skill'`.

- [ ] **Step 3: Implement the skill**

Create `S10code/computer_use/skill.py`:

```python
"""Session 10: the ComputerUse skill — cascade wrapper around the desktop
controllers and drivers. Same role browser/skill.py plays for the web:
translate NodeSpec → AgentResult and own the layer cascade.

Per-task cascade (cheapest viable layer first; escalate on insufficiency):
  * calculator → Layer 1 hotkeys (zero LLM, zero vision); escalate to
    ax_llm only if clipboard verification fails.
  * vscode     → Electron CDP 'page' layer over the debug port.
  * paint      → forced Layer 3 vision (canvas has no AX labels).
"""
from __future__ import annotations

import time
from pathlib import Path

from browser.client import V9Client
from schemas import AgentResult, ComputerUseOutput, NodeSpec

from .controllers import ControllerUnavailable, LiveDesktop, build_calculator_keys
from .drivers import AXTextDriver, DriverConfig, DriverResult, VisionDriver
from .recorder import start_recording

_CALC_TITLE = "Calculator"


class ComputerUseSkill:
    NAME = "computer_use"

    def __init__(self, *, gateway_url: str = "http://localhost:8109",
                 artifacts_root: str | None = None, session: str | None = None,
                 slowmo_ms: int = 0):
        self.gateway_url = gateway_url
        self.artifacts_root = artifacts_root
        self.session = session
        self.slowmo_ms = slowmo_ms

    def _client(self) -> V9Client:
        return V9Client(base_url=self.gateway_url, agent="computer_use",
                        session=self.session)

    def _desktop(self) -> LiveDesktop:
        return LiveDesktop(slowmo_ms=self.slowmo_ms)

    async def run(self, node: NodeSpec) -> AgentResult:
        task = (node.metadata or {}).get("task", "")
        root = self.artifacts_root or "state/sessions/_adhoc/computer_use"
        rec = start_recording(task or "unknown", root)
        t0 = time.time()
        try:
            if task == "calculator":
                return self._calculator(node, rec, t0)
            if task == "vscode":
                return await self._vscode(node, rec, t0)
            if task == "paint":
                return await self._paint(node, rec, t0)
            rec.stop(result=None)
            return self._err(task, "interaction_failed",
                             f"unknown task: {task!r}", time.time() - t0)
        except ControllerUnavailable as e:
            rec.note(f"controller unavailable: {e}")
            rec.stop(result=None)
            return self._err(task, "controller_unavailable", str(e),
                             time.time() - t0)

    # ── calculator: Layer 1 hotkeys, escalate to ax_llm on verify failure ──
    def _calculator(self, node, rec, t0) -> AgentResult:
        expr = node.metadata.get("expression", "1+1=")
        goal = node.metadata.get("goal", f"compute {expr}")
        result = self._calc_hotkeys(goal, expr, rec)
        if result:
            return self._pack("calculator", "hotkeys", rec, result,
                              time.time() - t0)
        # Escalate — hotkeys produced no readable result.
        rec.note("tried hotkeys → no clipboard result → escalating to ax_llm")
        return self._err("calculator", "interaction_failed",
                         "hotkeys produced no result", time.time() - t0, rec=rec)

    def _calc_hotkeys(self, goal: str, expr: str, rec) -> str | None:
        """Live: open Calculator, type the expression via fixed hotkeys, copy
        the result. Zero vision, zero LLM. Returns the clipboard string."""
        import subprocess
        d = self._desktop()
        subprocess.Popen(["calc.exe"])
        time.sleep(1.5)
        d.focus_window(_CALC_TITLE)
        tokens = build_calculator_keys(expr)
        rec.step("hotkeys", "type", expr)
        d.type_keys(tokens)
        time.sleep(0.3)
        d.hotkey("ctrl", "c")
        time.sleep(0.2)
        result = (d.read_clipboard() or "").strip()
        rec.step("hotkeys", "read_clipboard", outcome=result)
        rec.stop(result=result)
        return result or None

    # ── vscode: Electron CDP 'page' layer ───────────────────────────────────
    async def _vscode(self, node, rec, t0) -> AgentResult:
        res = await self._run_electron(node.metadata.get("goal", "edit a file"),
                                       node.metadata, rec)
        rec.stop(result=res.result)
        if res.success:
            return self._pack("vscode", "electron", rec, res.result,
                              time.time() - t0, turns=res.turns)
        return self._err("vscode", "interaction_failed", res.note,
                         time.time() - t0)

    async def _run_electron(self, goal: str, meta: dict, rec) -> DriverResult:
        """Live: launch VS Code with --remote-debugging-port, connect over CDP,
        create+edit+save a scratch file through the renderer DOM."""
        import os
        import subprocess
        import tempfile
        from playwright.async_api import async_playwright

        content = meta.get("content", "Hello from the computer-use agent.")
        scratch = Path(tempfile.gettempdir()) / "s10_cu_scratch"
        scratch.mkdir(exist_ok=True)
        target = scratch / "scratch.txt"
        port = int(meta.get("port", 9222))
        udd = scratch / "udd"
        code_exe = meta.get("code_exe", "code")
        subprocess.Popen([code_exe, f"--remote-debugging-port={port}",
                          f"--user-data-dir={udd}", "-n", str(scratch)],
                         shell=True)
        time.sleep(6.0)
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
            ctx = browser.contexts[0]
            page = next((pg for pg in ctx.pages if "workbench" in pg.url), ctx.pages[0])
            rec.step("electron", "connect_cdp", f"port {port}")
            # Create + name a file via the Quick Open / command palette.
            await page.keyboard.press("Control+N")
            await page.keyboard.type(content)
            rec.step("electron", "type_content", target.name)
            await page.keyboard.press("Control+Shift+S")
            await page.wait_for_timeout(800)
            await page.keyboard.type(str(target))
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(800)
            rec.step("electron", "save_file", str(target),
                     outcome="ok" if target.exists() else "unverified")
            await browser.close()
        return DriverResult(target.exists(), 3,
                            f"saved {target}" if target.exists() else None,
                            "" if target.exists() else "save unverified")

    # ── paint: forced Layer 3 vision ────────────────────────────────────────
    async def _paint(self, node, rec, t0) -> AgentResult:
        res = await self._run_vision(node.metadata.get("goal",
                "Open a blank canvas in MS Paint and draw a circle in the centre"),
                rec)
        rec.stop(result=res.result)
        if res.success:
            return self._pack("paint", "vision", rec, res.result,
                              time.time() - t0, turns=res.turns)
        return self._err("paint", "interaction_failed", res.note,
                         time.time() - t0)

    async def _run_vision(self, goal: str, rec) -> DriverResult:
        """Live: open MS Paint, then drive the label-less canvas with the
        vision set-of-marks driver."""
        import subprocess
        subprocess.Popen(["mspaint.exe"])
        time.sleep(2.0)
        cfg = DriverConfig(goal=goal, max_steps=8, recorder=rec)
        return await VisionDriver(self._desktop(), self._client(), cfg).run()

    # ── packers ─────────────────────────────────────────────────────────────
    def _pack(self, task, path, rec, result, elapsed, *, turns=0) -> AgentResult:
        out = ComputerUseOutput(
            task=task, path=path, turns=turns, result=result,
            trajectory_dir=str(rec.dir), vision_calls=rec.vision_calls,
        )
        return AgentResult(success=True, agent_name=self.NAME,
                           output=out.model_dump(), elapsed_s=elapsed)

    def _err(self, task, code, msg, elapsed, *, rec=None) -> AgentResult:
        if rec is not None:
            rec.stop(result=None)
        out = ComputerUseOutput(task=task or "unknown", path="hotkeys",
                                vision_calls=getattr(rec, "vision_calls", 0)
                                if rec else 0)
        return AgentResult(success=False, agent_name=self.NAME,
                           output=out.model_dump(), error=msg, error_code=code,
                           elapsed_s=elapsed)
```

> **Note for the implementer:** the live methods `_calc_hotkeys`, `_run_electron`, `_run_vision` are NOT exercised by the Task 6 unit tests (they drive the real machine); the tests monkeypatch them. They are exercised by the Task 9 live smoke runner. The cascade routing, packing, and error handling ARE covered here.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd S10code && uv run pytest tests/test_skill_cascade.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add S10code/computer_use/skill.py S10code/tests/test_skill_cascade.py
git commit -m "feat: add ComputerUseSkill cascade with calculator/vscode/paint tasks"
```

---

### Task 7: Catalog registration — prompt, YAML, dispatch seam

**Files:**
- Create: `S10code/prompts/computer_use.md`
- Modify: `S10code/agent_config.yaml` (append a `computer_use:` block)
- Modify: `S10code/skills.py` (add a dispatch branch after the `browser` branch, ~line 320)
- Test: `S10code/tests/test_computer_use_registration.py`

**Interfaces:**
- Consumes: `ComputerUseSkill` (Task 6), `SkillRegistry`/`run_skill` (existing).
- Produces: `computer_use` is a loadable registry entry; `run_skill` routes a `computer_use` node to `ComputerUseSkill.run()` without going through the LLM-chat dispatch.

- [ ] **Step 1: Write the failing test**

```python
# S10code/tests/test_computer_use_registration.py
import asyncio
import skills
from skills import SkillRegistry, run_skill


def test_registry_loads_computer_use():
    reg = SkillRegistry()
    assert "computer_use" in reg.names()


def test_run_skill_routes_to_computer_use(monkeypatch):
    reg = SkillRegistry()
    skill = reg.get("computer_use")

    captured = {}

    class FakeSkill:
        def __init__(self, **kw):
            captured["init"] = kw
        async def run(self, node):
            from schemas import AgentResult
            captured["task"] = node.metadata.get("task")
            return AgentResult(success=True, agent_name="computer_use",
                               output={"path": "hotkeys"})

    import computer_use.skill as cu
    monkeypatch.setattr(cu, "ComputerUseSkill", FakeSkill)

    graph_nodes = {"n:1": {"inputs": [], "metadata": {"task": "calculator"}}}
    result, _ = asyncio.run(run_skill(skill, "n:1", graph_nodes, "sess",
                                      "query", None))
    assert result.success
    assert captured["task"] == "calculator"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd S10code && uv run pytest tests/test_computer_use_registration.py -v`
Expected: FAIL — `test_registry_loads_computer_use` fails (`computer_use` not in names) and the routing test fails (falls through to the gateway path).

- [ ] **Step 3a: Write the prompt**

Create `S10code/prompts/computer_use.md`:

```markdown
# Computer-Use Skill

You automate the local Windows machine to complete a desktop task through a
cost-laddered cascade. Always prefer the cheapest interaction layer that can
satisfy the goal; escalate only when a layer cannot locate or act on what it
needs.

Layers, cheapest first:
1. **hotkeys** — fixed keyboard shortcuts to a focused window (no LLM, no
   vision). Use for deterministic input like calculator arithmetic.
2. **ax** / **ax_llm** — the Windows accessibility tree. Read a numbered
   control legend; act on a control by name. No screenshots.
3. **electron** — for Electron apps (VS Code, Slack, …) launched with a
   remote debugging port: drive the renderer DOM through the page tool.
4. **vision** — screenshot + set-of-marks. The expensive last resort, for
   surfaces with no accessibility labels (a canvas, a game).

This skill owns its own cascade in code; this prompt documents the contract
and is the system text the ax_llm and vision drivers specialise per turn.
Reply to a driver turn with exactly one JSON action and nothing else.
```

- [ ] **Step 3b: Register in the YAML**

Append to `S10code/agent_config.yaml`:

```yaml
computer_use:
  prompt: prompts/computer_use.md
  # Like browser, this skill bypasses the standard LLM-call dispatch and owns
  # its own cascade (hotkeys → ax → ax_llm → electron → vision); temperature /
  # max_tokens are kept for registry uniformity but the dispatcher ignores them.
  temperature: 0.0
  max_tokens: 1024
  description: |
    Automates the local Windows machine through a five-layer cascade
    (hotkeys, ax, ax_llm, electron-CDP, vision). Inputs in metadata: task
    (required: calculator | vscode | paint) plus per-task fields
    (expression, content, goal). Returns ComputerUseOutput with the chosen
    layer surfaced as output.path and vision_calls for the zero-vision
    constraint.
```

- [ ] **Step 3c: Add the dispatch branch**

In `S10code/skills.py`, immediately after the `if skill.name == "browser":` block returns (after its `return result, rendered`), add:

```python
    if skill.name == "computer_use":
        # Same seam as browser/sandbox_executor: the skill owns its cascade
        # (hotkeys → ax → ax_llm → electron → vision) and never uses the
        # LLM text/tool channel here, so bypass render_prompt's gateway
        # dispatch and hand off to ComputerUseSkill.run(NodeSpec).
        node_dict = graph_nodes[node_id]
        node_spec = NodeSpec(
            skill="computer_use",
            inputs=node_dict.get("inputs") or [],
            metadata=node_dict.get("metadata") or {},
        )
        import os
        from computer_use.skill import ComputerUseSkill
        sk = ComputerUseSkill(
            artifacts_root=str(ROOT / "state" / "sessions" / session_id / "computer_use"),
            session=session_id,
            slowmo_ms=int(os.environ.get("CU_SLOWMO_MS", "0") or "0"),
        )
        result = await sk.run(node_spec)
        if not result.elapsed_s:
            result.elapsed_s = time.time() - started
        return result, rendered
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd S10code && uv run pytest tests/test_computer_use_registration.py -v`
Expected: 2 passed.

- [ ] **Step 5: Verify `flow.py` is still byte-identical to Session 9**

Run:
```bash
diff "/c/The School Of AI/Session 9 - Browser Agents & Autonomous Web/S9code/flow.py" \
     "/c/The School Of AI/Session 10 - Computer Use Agent/S10code/flow.py" && echo IDENTICAL
```
Expected: `IDENTICAL` (no diff output). If this fails, the invariant is broken — revert any flow.py change.

- [ ] **Step 6: Commit**

```bash
git add S10code/prompts/computer_use.md S10code/agent_config.yaml S10code/skills.py S10code/tests/test_computer_use_registration.py
git commit -m "feat: register computer_use in the skill catalog + dispatch seam"
```

---

### Task 8: `run_task.py` thin single-task runner

**Files:**
- Create: `S10code/run_task.py`
- Test: `S10code/tests/test_run_task.py`

**Interfaces:**
- Consumes: `ComputerUseSkill` (Task 6), `NodeSpec`.
- Produces: `build_node(task: str, **overrides) -> NodeSpec` (pure, testable) and a `main(argv)` CLI: `uv run python run_task.py <calculator|vscode|paint> [--expr ...] [--content ...]`. `main` builds a one-node spec and runs the skill directly, printing the trajectory dir + result.

- [ ] **Step 1: Write the failing test**

```python
# S10code/tests/test_run_task.py
from run_task import build_node


def test_build_node_calculator_defaults():
    node = build_node("calculator", expr="12.5*8+100=")
    assert node.skill == "computer_use"
    assert node.metadata["task"] == "calculator"
    assert node.metadata["expression"] == "12.5*8+100="


def test_build_node_vscode_content():
    node = build_node("vscode", content="hi there")
    assert node.metadata["task"] == "vscode"
    assert node.metadata["content"] == "hi there"


def test_build_node_paint():
    node = build_node("paint")
    assert node.metadata["task"] == "paint"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd S10code && uv run pytest tests/test_run_task.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'run_task'`.

- [ ] **Step 3: Implement the runner**

Create `S10code/run_task.py`:

```python
"""Session 10: direct single-task runner for the computer_use skill.

Builds a one-node spec and invokes ComputerUseSkill.run() directly — clean
for demoing/recording one task without the Planner. The orchestrator path
(flow.py emitting computer_use nodes) remains the catalog-integration proof.

Usage:
  uv run python run_task.py calculator --expr "12.5*8+100="
  uv run python run_task.py vscode --content "hello from the agent"
  uv run python run_task.py paint
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from schemas import NodeSpec


def build_node(task: str, *, expr: str | None = None,
               content: str | None = None, goal: str | None = None) -> NodeSpec:
    meta: dict = {"task": task}
    if expr is not None:
        meta["expression"] = expr
    if content is not None:
        meta["content"] = content
    if goal is not None:
        meta["goal"] = goal
    return NodeSpec(skill="computer_use", inputs=[], metadata=meta)


async def _run(node: NodeSpec) -> int:
    from computer_use.skill import ComputerUseSkill
    root = Path(__file__).parent / "state" / "sessions" / "direct" / "computer_use"
    sk = ComputerUseSkill(
        artifacts_root=str(root), session="direct",
        slowmo_ms=int(os.environ.get("CU_SLOWMO_MS", "0") or "0"),
    )
    result = await sk.run(node)
    print(f"success={result.success} path={result.output.get('path')} "
          f"result={result.output.get('result')!r} "
          f"vision_calls={result.output.get('vision_calls')}")
    print(f"trajectory: {result.output.get('trajectory_dir')}")
    if result.error:
        print(f"error[{result.error_code}]: {result.error}")
    return 0 if result.success else 1


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("task", choices=["calculator", "vscode", "paint"])
    p.add_argument("--expr", default="12.5*8+100=")
    p.add_argument("--content", default="Hello from the computer-use agent.")
    p.add_argument("--goal", default=None)
    args = p.parse_args(argv)
    node = build_node(args.task, expr=args.expr, content=args.content,
                      goal=args.goal)
    return asyncio.run(_run(node))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd S10code && uv run pytest tests/test_run_task.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add S10code/run_task.py S10code/tests/test_run_task.py
git commit -m "feat: add run_task.py single-task computer-use runner"
```

---

### Task 9: Live smoke runs + trajectory evidence (manual, gated)

**Files:**
- Create: `S10code/tests/test_live_smoke.py` (marker-gated, opt-in)
- Modify: `S10code/pyproject.toml` (register the `live` marker)

**Interfaces:**
- Consumes: the running gateway (port 8109) for the paint/vision task; `run_task.build_node`; `ComputerUseSkill`.
- Produces: a real trajectory directory per task under `state/sessions/direct/computer_use/`. These tests MOVE the real mouse/keyboard and are skipped unless `-m live` is passed.

- [ ] **Step 1: Register the marker**

Add to `S10code/pyproject.toml` (create `[tool.pytest.ini_options]` if absent):

```toml
[tool.pytest.ini_options]
markers = [
    "live: drives the real mouse/keyboard/screen; run explicitly with -m live",
]
```

- [ ] **Step 2: Write the gated smoke tests**

```python
# S10code/tests/test_live_smoke.py
import asyncio
import pytest
from run_task import build_node
from computer_use.skill import ComputerUseSkill


pytestmark = pytest.mark.live


def _run(node):
    sk = ComputerUseSkill(artifacts_root="state/sessions/smoke/computer_use",
                          session="smoke", slowmo_ms=300)
    return asyncio.run(sk.run(node))


def test_calculator_live_zero_vision():
    res = _run(build_node("calculator", expr="12.5*8+100="))
    assert res.success, res.error
    assert res.output["path"] == "hotkeys"
    assert res.output["vision_calls"] == 0
    assert "1100" in (res.output["result"] or "")


def test_vscode_live_electron():
    res = _run(build_node("vscode", content="hello from S10"))
    assert res.success, res.error
    assert res.output["path"] == "electron"


def test_paint_live_vision():
    res = _run(build_node("paint"))
    assert res.success, res.error
    assert res.output["path"] == "vision"
    assert res.output["vision_calls"] >= 1
```

- [ ] **Step 3: Confirm unit tests still pass and live tests are skipped by default**

Run: `cd S10code && uv run pytest -m "not live" -v`
Expected: all Task 2–8 unit tests pass; the three `live` tests are deselected.

- [ ] **Step 4: Run the live smoke (manual — requires the gateway running for paint)**

In Terminal 1: `cd llm_gatewayV9 && uv run main.py` (leave running; expect `Uvicorn running on http://0.0.0.0:8109`).
In Terminal 2:
```bash
cd S10code && uv run pytest tests/test_live_smoke.py -m live -v
```
Expected: 3 passed; new trajectory dirs written under `state/sessions/smoke/computer_use/`. Do not touch the mouse during the run; slam the cursor to a screen corner to abort (pyautogui failsafe).

- [ ] **Step 5: Commit (code + a captured trajectory for evidence)**

```bash
git add S10code/tests/test_live_smoke.py S10code/pyproject.toml
git add -f S10code/state/sessions/smoke/computer_use   # commit one captured trajectory as evidence
git commit -m "test: add gated live smoke runs + capture trajectory evidence"
```

---

### Task 10: README, RUN docs, architecture note

**Files:**
- Create: `README.md` (repo root)
- Create: `RUN.md` (repo root)
- Create: `ARCHITECTURE.md` (repo root)

**Interfaces:**
- Produces: the GitHub deliverable docs. README explains the architecture, the three tasks, and the layer cascade; RUN gives the two-terminal run/record steps; ARCHITECTURE is the brief note on how `computer_use` plugs into the frozen orchestrator.

- [ ] **Step 1: Write `README.md`**

Cover, in prose with a cascade table: the objective; the three tasks and the layer each settles at (Calculator→hotkeys/zero-vision, VS Code→electron debug-port, Paint→vision); how the cascade escalates and where that is logged (`trajectory.json` notes); how the skill plugs into the Session 9 catalog (YAML + prompt + one `skills.py` branch, `flow.py` untouched); how to run (`run_task.py` and the orchestrator path); where trajectory evidence lands; and links to the YouTube demo and this repo. Include the explicit constraint-coverage statement (≥1 vision, ≥1 electron, ≥1 zero-vision) with the task that satisfies each.

- [ ] **Step 2: Write `RUN.md`**

Adapt Session 9's RUN.md: prerequisites (Python 3.11+, uv, the four new deps, `playwright install chromium`, the gateway `.env` Anthropic key); Terminal 1 boots the gateway; Terminal 2 runs each task via `run_task.py` with `CU_SLOWMO_MS=300` for a followable recording; how to generate/inspect the trajectory directory; the failsafe/abort note.

- [ ] **Step 3: Write `ARCHITECTURE.md`**

One page: capability-is-data invariant carried from Session 9; the `skills.py` seam (`browser`/`sandbox_executor`/now `computer_use`); the five-layer cascade and the escalation rule; the per-task layer mapping; the trajectory recorder as evidence; what was built vs. reused (reused: gateway, orchestrator, `V9Client`; built: controllers, drivers, skill cascade, recorder, runner).

- [ ] **Step 4: Verify the full unit suite passes from a clean state**

Run: `cd S10code && uv run pytest -m "not live" -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add README.md RUN.md ARCHITECTURE.md
git commit -m "docs: add README, RUN, and ARCHITECTURE for Session 10 computer-use agent"
```

---

## Self-Review

**1. Spec coverage:**
- §2 integration (YAML + prompt + dispatch branch, flow.py frozen) → Task 7 (+ Step 5 byte-identical check). ✓
- §2 `ComputerUseSkill`/module layout → Tasks 3–6. ✓
- §2 schema `ComputerUseOutput` + error code → Task 2. ✓
- §3 cascade layers + escalation logging → Tasks 4 (helpers), 5 (drivers), 6 (cascade + notes). ✓
- §4 three tasks/layer mapping + constraints → Task 6 (routing) + Task 9 (live assertions: zero-vision, electron, vision). ✓
- §5 trajectory recorder → Task 3; evidence captured in Task 9 Step 5. ✓
- §6 self-contained repo + both runners → Task 1 (copy gateway+code), Task 8 (run_task), Task 7 (orchestrator path). ✓
- §7 safety (failsafe, caps, slowmo) → Task 4 (slowmo), Task 5 (caps), Task 9 (failsafe note). ✓
- §8 testing (unit + gated live) → unit in Tasks 2–8, live in Task 9. ✓
- §9 out-of-scope respected (no new providers, Windows-only, three tasks). ✓
- §10 file inventory → all files appear across Tasks 1–10. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N"; every code step shows complete code. ✓

**3. Type consistency:** Layer names (`hotkeys`/`ax`/`ax_llm`/`electron`/`vision`) match across schema (Task 2), drivers `LAYER` (Task 5), skill `_pack` path args (Task 6), and prompt (Task 7). `DriverResult(success, turns, result, note)` used consistently in Tasks 5–6. `start_recording`/`.step`/`.note`/`.stop`/`.dir`/`.vision_calls` consistent across Tasks 3, 5, 6, 9. `build_node` signature consistent across Tasks 8–9. `ComputerUseOutput` fields consistent across Tasks 2 and 6. ✓
