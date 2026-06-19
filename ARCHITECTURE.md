# Architecture Note — Session 10 Computer-Use Agent

This note explains how the `computer_use` skill plugs into the frozen Session 9
orchestrator, how the five-layer cascade works, and what was built versus reused.

## 1. The orchestrator is frozen; capability is data

The Session 8/9 engine is a **growing-graph orchestrator** (`flow.py`). The
Planner emits a small DAG of skill nodes; the Executor runs every ready node in
parallel via `asyncio.gather`; the graph grows at runtime from five sources
(Planner seed, dynamic successors, static `internal_successors`, auto-Critic
insertion, recovery re-planning). There is no hand-written `while` loop — the
agent loop is an emergent property of the graph shape.

**A skill is two files, not a Python class:** a block in `agent_config.yaml` +
a prompt `.md`. Adding a capability means adding **data**, not editing the
engine.

**Invariant honored:** `flow.py` is byte-identical to Session 9. The
`computer_use` capability is added entirely through (a) data — a YAML block and
a prompt — and (b) one pre-existing extension seam in `S10code/skills.py`.

## 2. The `S10code/skills.py` dispatch seam

`S10code/skills.py` dispatches most skills by rendering their prompt and calling the
gateway's `/v1/chat`. Two pre-existing branches bypass that channel for skills
that own their own control loop: `sandbox_executor` (runs Python code) and
`browser` (runs the four-layer web cascade). Session 10 adds a third:

```
if skill.name == "sandbox_executor": → sandbox.run_python
if skill.name == "browser":          → BrowserSkill.run(NodeSpec)
if skill.name == "computer_use":     → ComputerUseSkill.run(NodeSpec)   ← S10
# all other skills → gateway /v1/chat
```

The `computer_use` branch (lines 322–343 of `S10code/skills.py`) builds a `NodeSpec`
from the node's `inputs` and `metadata`, instantiates `ComputerUseSkill`, and
returns the typed `AgentResult`. The orchestrator never learns what a desktop
is — it just schedules a node and receives the same shaped result it receives
from every other skill.

## 3. The five-layer cascade

A cost ladder — cheapest viable layer first, escalate only on insufficiency:

| Layer | Mechanism | Cost | Tooling |
|---|---|---|---|
| **hotkeys** | Hardcoded keystrokes to focused window; read result via clipboard | No LLM, no vision | `pyautogui`, `pyperclip` |
| **ax** | UIAutomation: find control by name, `Invoke()` directly | No LLM, no vision | `pywinauto` (uia backend) |
| **ax_llm** | AX tree serialised → numbered legend → `/v1/chat`; LLM picks one action per turn | Text LLM, no image | `pywinauto` + `V9Client.chat` |
| **electron** | Launch app with `--remote-debugging-port`, `connect_over_cdp`, drive renderer DOM | No vision | `playwright` |
| **vision** | Screenshot → `/v1/vision` (coordinate-based); act on returned pixel coords | Vision LLM (expensive — last resort) | `mss`/`Pillow` + `V9Client.vision` |

**Escalation rule:** stop at the first layer that completes the goal. Escalate
when the current layer's locate/act step fails or returns an empty result.
Every escalation decision is logged as a human-readable string in
`trajectory.json`'s `notes` list.

### Per-task layer mapping

| Task | Settles at | Why |
|---|---|---|
| **Calculator** | hotkeys | Fixed arithmetic expression → deterministic keystrokes; clipboard returns the result. If clipboard is empty the run fails cleanly. An `ax_llm` fallback is a documented extension point (not implemented, since the hotkeys + clipboard path is deterministic). Vision is never needed. |
| **VS Code** | electron | VS Code is an Electron app; launched with `--remote-debugging-port=9222`; Playwright `connect_over_cdp` drives the renderer DOM to create, type into, and save a file. |
| **MS Paint** | vision | The canvas has no accessibility labels; a raw screenshot is sent to the vision LLM, which returns pixel coordinates for the agent to act on (coordinate-based vision, not set-of-marks annotation). |

## 4. The trajectory recorder (`recorder.py`)

`TrajectoryRecorder` is the assignment's evidence instrument. API:

```python
rec = start_recording(task, root)   # creates <root>/<task>_<n>/
rec.step(layer, action, target, outcome, screen_png=..., vision_called=...)
rec.note("escalation message")
rec.stop(result=...)                # flushes trajectory.json
```

Each run directory contains:
- `step_NN.json` — per-step record.
- `step_NN_screen.png` — raw screenshot (vision steps only; the current `VisionDriver` uses coordinate-based vision and does not produce set-of-marks annotation).
- `step_NN_marked.png` — written only when a marked image is supplied to `rec.step()`; the recorder supports it, but the current `VisionDriver` does not emit one.
- `trajectory.json` — ordered step log, `layer_counts`, `vision_calls` (the
  zero-vision assertion field), `notes` (escalation log), and final `result`.

Run directories land under:
`state/sessions/<session-id>/computer_use/<task>_<n>/`

## 5. What was built vs. reused

| | |
|---|---|
| **Built (Session 10)** | `computer_use/skill.py` (cascade + three task methods); `computer_use/controllers.py` (LiveDesktop wrappers + pure helpers); `computer_use/drivers.py` (AXTextDriver, VisionDriver bounded loops); `computer_use/recorder.py` (TrajectoryRecorder); `run_task.py` (direct single-task runner); `prompts/computer_use.md`; `ComputerUseOutput` schema; `computer_use:` YAML block; dispatch branch in `S10code/skills.py`; unit test suite |
| **Reused unchanged** | `llm_gatewayV9/` (port 8109, Anthropic provider, vision endpoint); `flow.py`, `recovery.py`, `persistence.py` (frozen orchestrator); `browser/client.py` `V9Client` (imported directly — not duplicated); all Session 9 skills and their prompts |
