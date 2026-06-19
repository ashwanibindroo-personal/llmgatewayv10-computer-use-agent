# Session 10 — Computer-Use Agent: Design

> ⚠️ **Historical design record — partially superseded.** This is the *original*
> design, kept for process history. Two tasks were re-targeted during live
> testing on Windows 11: the Electron task moved from **VS Code** to a bundled
> minimal Electron app (modern VS Code doesn't expose its renderer to CDP), and
> the vision task moved from **MS Paint** to a label-less **HTML canvas** driven
> by **set-of-marks** (pyautogui can't draw in Win11 Paint; raw-coordinate vision
> is too imprecise). For the current, authoritative description see
> [`README.md`](../../../README.md) and [`ARCHITECTURE.md`](../../../ARCHITECTURE.md).

**Date:** 2026-06-19
**Status:** Approved (brainstorming) → pending spec review

## 1. Objective

Add a **`computer_use`** skill to the Session 9 DAG skill catalog (copied into a
self-contained Session 10 repo) that automates the **local Windows 11 machine**
through a cost-laddered **cascade**, completing **three tasks** and proving
*cascade discipline* (always try the cheapest interaction layer first, escalate
only on insufficiency) plus *trajectory recording*.

### Assignment constraints (all satisfied — see §4)
- ≥1 task uses **vision** (Layer 3).
- ≥1 task uses the **Electron debugging port** path.
- ≥1 task uses **zero vision calls** (text/hotkeys only).

### Deliverables
- Public **GitHub repo** + `README.md` (architecture, the 3 tasks, how the layer
  cascade works) — 1,000 pts.
- Public **YouTube demo** showing ≥1 task executing live on screen — 1,000 pts.
- **Trajectory directory** produced by `start_recording` during the runs.

## 2. Integration — mirror the `browser` skill exactly

The new skill plugs into the frozen Session 8/9 orchestrator the same way
`browser` and `sandbox_executor` do — **capability is data + one dispatch
branch**, never an orchestrator edit.

1. **YAML block** `computer_use:` in `agent_config.yaml` (prompt path,
   description, temperature/max_tokens kept for registry uniformity though the
   dispatcher ignores them — same as `browser`).
2. **Prompt** `prompts/computer_use.md`.
3. **Dispatch seam** in `skills.py`: an `if skill.name == "computer_use":`
   branch that constructs a `NodeSpec` from the node's `inputs`/`metadata` and
   hands off to `ComputerUseSkill.run()`, returning a typed `AgentResult` — the
   identical shape the orchestrator already receives from `browser`.
4. **New module** `computer_use/` mirroring `browser/`:
   - `skill.py` — `ComputerUseSkill`, the cascade wrapper + per-task entry.
   - `controllers.py` — low-level OS controllers: hotkeys/clicks/clipboard,
     UIAutomation AX tree, Electron CDP connector, screen capture.
   - `drivers.py` — bounded per-layer driver loops (AX-text driver, vision
     set-of-marks driver), following `browser/driver.py`'s loop shape
     (step cap, consecutive-failure cap, wall-clock cap, per-step evidence).
   - `recorder.py` — `TrajectoryRecorder` implementing `start_recording`.
   - reuse `browser/client.py` `V9Client` verbatim (import; do not duplicate).
5. **Schema** `ComputerUseOutput` added to `schemas.py` — additive, modelled on
   `BrowserOutput`, carrying `path` (the layer actually used), `task`,
   `actions`, `turns`, `result`, `trajectory_dir`, and `vision_calls`.

**Invariant honored:** `flow.py` stays byte-identical to Session 8/9. No agent
framework — controllers are hand-written over `pyautogui`/`pywinauto`/
`playwright`.

## 3. The cascade (cost ladder, desktop-adapted)

Same discipline as `browser/skill.py`: try the cheapest sense first; a layer
escalates only when it cannot locate or act on the needed control. Each step
logs `tried layer X → insufficient (reason) → escalating to layer Y` into the
trajectory so the discipline is **visible** in the evidence.

| Layer | Mechanism | Cost | Tooling |
|---|---|---|---|
| **1 — hotkeys / deterministic** | hardcoded keystrokes to the focused window; read result via clipboard | no LLM, no vision | `pyautogui`, `pyperclip` |
| **2a — AX tree (no LLM)** | UIAutomation: find a control by name and `Invoke()` it directly | no LLM, no vision | `pywinauto` (uia backend) |
| **2b — AX tree + cheap text LLM** | serialize the AX tree → numbered legend → `/v1/chat`; LLM picks one action per turn | text LLM, no image tokens | `pywinauto` + `V9Client.chat` |
| **Electron (CDP `page`)** | launch the app with `--remote-debugging-port`, `connect_over_cdp`, drive the renderer DOM with a `page`-like tool | no vision | `playwright` |
| **3 — vision (set-of-marks)** | screenshot → annotate with numbered marks → `/v1/vision` → act on the returned mark / pixel coords | vision LLM (expensive — last resort) | `mss`/`Pillow` + `V9Client.vision` |

**Escalation rule:** stop at the first layer that completes the goal. Escalate
when the current layer's locate/act step fails or its output is empty.

## 4. The three tasks → layer mapping

| Task | Settles at | Constraint satisfied |
|---|---|---|
| **Calculator** (Windows Calculator) — compute a fixed expression, read result via clipboard | **Layer 1 hotkeys** (zero LLM, zero vision); escalates to 2b only if clipboard verification fails | **zero-vision** — trajectory asserts `vision_calls == 0` |
| **VS Code** (Electron) — open a scratch file in a temp folder, type content, save, via the renderer DOM | **Electron CDP layer** (`page` tool over `--remote-debugging-port=9222`); escalates to vision only if CDP is unavailable | **Electron debug-port** |
| **MS Paint** — draw a target shape on the canvas | AX for toolbar tool-select where labels exist, then **forced Layer 3 vision** for the label-less canvas (locate canvas region, draw at vision-returned coords) | **vision (Layer 3)** |

## 5. Trajectory recording — `start_recording`

`TrajectoryRecorder` writes under
`state/sessions/<sid>/computer_use/<task>_<ts>/`, mirroring `browser`'s
per-turn artifact convention:
- `step_NN_screen.png` — raw screenshot each step.
- `step_NN_marked.png` — annotated screenshot (vision steps only).
- `step_NN.json` — `{layer, action, target, outcome, vision_called}`.
- `trajectory.json` — ordered step log + per-layer call counts +
  the zero-vision assertion for Calculator + final `result`.

API: `rec = start_recording(task, root)` → records steps via
`rec.step(...)` → `rec.stop()` flushes `trajectory.json`. This directory is the
submission artifact (deliverable evidence).

## 6. Running & recording

- The Session 10 repo is **self-contained**: copy `S9code` → `S10code` and
  `llm_gatewayV9` into Session 10; reuse the existing Anthropic key. RUN.md
  explains booting the gateway (port 8109) in one terminal, the agent in
  another — same two-terminal flow as Session 9.
- **Both runners kept:**
  - Orchestrator path — the Planner can emit `computer_use` nodes; proves the
    skill is a real catalog member (`uv run python flow.py "<query>"`).
  - `run_task.py <calculator|vscode|paint>` — a thin runner that builds a
    single-node graph and invokes the skill directly, for clean, isolated
    demo/recording of each task without depending on Planner decomposition.

## 7. Safety / reliability for live runs

- `pyautogui` failsafe enabled (slam mouse to a screen corner to abort).
- Per-driver step cap, consecutive-failure cap, and wall-clock cap (as in
  `browser/driver.py`).
- Each task is idempotent and self-contained: Calculator opens fresh; VS Code
  uses a temp scratch folder; Paint draws on a blank canvas.
- A configurable inter-action slow-mo (env, like `BROWSER_SLOWMO_MS`) so a
  screen recording can follow the actions.

## 8. Testing

- **Unit (no machine control):** AX-legend serializer; hotkey-sequence builder;
  `TrajectoryRecorder` write/flush; the zero-vision assertion logic; the
  `ComputerUseOutput` schema round-trip.
- **Live smoke (moves real mouse/keyboard — marker-gated, opt-in):** each of the
  three tasks end-to-end on the local machine.

## 9. Out of scope (YAGNI)

- No cross-platform (mac/Linux) controllers — Windows 11 only, the user's main OS.
- No new gateway providers or routing changes — reuse Session 9's gateway as-is.
- No additional tasks beyond the three; the other three of the six options are
  not built.
- No orchestrator/`flow.py` changes — the frozen-engine invariant holds.

## 10. Module/file inventory (new or modified in S10code)

- `agent_config.yaml` — **+** `computer_use:` block.
- `schemas.py` — **+** `ComputerUseOutput`; possibly **+** an `ErrorCode`
  member (`controller_unavailable`) — additive only.
- `skills.py` — **+** `computer_use` dispatch branch (mirrors `browser`).
- `computer_use/__init__.py`, `skill.py`, `controllers.py`, `drivers.py`,
  `recorder.py` — **new**.
- `prompts/computer_use.md` — **new** (drives Layer 2b / vision action choice).
- `run_task.py` — **new** thin single-task runner.
- `tests/test_computer_use_*.py` — **new** unit tests.
- `requirements.txt` / `pyproject.toml` — **+** `pyautogui`, `pyperclip`,
  `pywinauto`, `mss` (Pillow + playwright already present from S9).
- `README.md`, `RUN.md` — **new/adapted** for Session 10 deliverables.
