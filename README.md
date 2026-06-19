# Session 10 — Computer-Use Agent

A **`computer_use`** skill added to the Session 9 DAG skill catalog that
automates the **local Windows 11 machine** through a cost-laddered cascade,
completing three desktop tasks and producing trajectory evidence of cascade
discipline.

**Demo video:** _(YouTube link — add after recording)_

**Repo:** https://github.com/ashwanibindroo-personal/llmgatewayv10-computer-use-agent

---

## Objective

Prove that a complex OS-automation capability can be added to a frozen
growing-graph orchestrator as **data + one dispatch branch**, without touching
the orchestrator itself. The three tasks together satisfy all three assignment
constraints (vision, Electron debug-port, zero-vision).

---

## The Three Tasks and Their Layers

| Task | Settles at layer | Constraint satisfied |
|---|---|---|
| **Calculator** — compute an arithmetic expression, read result via clipboard | **hotkeys** (Layer 1 — zero LLM, zero vision) | **zero-vision** (`vision_calls == 0`) |
| **Electron app** — launch the bundled minimal Electron app (`S10code/electron_app/`), type content into `#editor`, read back and verify, persist to `electron_out.txt` | **electron** (CDP over `--remote-debugging-port=9222`) | **Electron debug-port** |
| **MS Paint** — open a blank canvas and draw a circle in the centre | **vision** (Layer 5 / last resort — screenshot + coordinate-based vision) | **vision (≥1 vision call)** |

### Constraint coverage (explicit)

- **≥1 vision call** — MS Paint task; the `VisionDriver` sends a raw
  screenshot and asks for pixel coordinates per turn (coordinate-based vision,
  not set-of-marks annotation); `trajectory.json` records `vision_calls > 0`.
- **≥1 Electron debug-port** — Electron app task; a bundled minimal Electron
  app shipped in `S10code/electron_app/` is launched with
  `--remote-debugging-port=9222`; Playwright `connect_over_cdp` drives the
  renderer DOM via the page tool.
- **≥1 zero-vision** — Calculator task; hotkeys + clipboard only;
  `trajectory.json` records `vision_calls == 0`.

---

## The Cascade

The cascade runs cheapest viable layer first; it escalates only when a layer
cannot locate or act on what it needs. Each escalation is logged as a human-
readable note in `trajectory.json` under the `notes` key, so the discipline
is visible in the evidence.

```
Layer 1 — hotkeys            pyautogui keystrokes + clipboard read
Layer 2a — ax                pywinauto UIAutomation Invoke (no LLM)
Layer 2b — ax_llm            AX tree serialised → numbered legend → V9Client.chat
Layer 3  — electron          connect_over_cdp → renderer DOM (Playwright)
Layer 4  — vision            mss screenshot → V9Client.vision (coordinate-based)
```

**Escalation rule:** stop at the first layer that completes the goal. Escalate
when the current layer's locate/act step fails or returns an empty result. The
Calculator task settles at the hotkeys layer; if the clipboard returns an empty
string the run fails cleanly. An `ax_llm` fallback is a documented extension
point (not implemented, since the hotkeys + clipboard path is deterministic).

### Where cascade evidence is recorded

`trajectory.json` in every run directory contains:

- `notes` — free-text log of every escalation decision (e.g.
  `"tried hotkeys → no clipboard result → failing (ax_llm fallback is a documented extension point, not implemented)"`).
- `layer_counts` — dict of `{layer_name: step_count}` for the run.
- `vision_calls` — integer count of `/v1/vision` invocations; the zero-vision
  assertion checks this field.
- `steps` — ordered list of per-step records, each with `{layer, action,
  target, outcome, vision_called}`.

---

## How `computer_use` Plugs into the Session 9 Catalog

The skill is added as **capability is data** — no changes to `flow.py`:

1. **YAML block** — `agent_config.yaml` (the `computer_use:` entry at the
   bottom, mirroring the `browser:` block):
   ```yaml
   computer_use:
     prompt: prompts/computer_use.md
     temperature: 0.0
     max_tokens: 1024
     description: |
       Automates the local Windows machine through a five-layer cascade
       (hotkeys, ax, ax_llm, electron-CDP, vision). ...
   ```

2. **Prompt** — `prompts/computer_use.md` documents the cascade contract and
   is the system text the `ax_llm` and vision drivers specialise per turn.

3. **One dispatch branch in `skills.py`** — the `if skill.name == "computer_use":` block (lines 322–343 of `S10code/skills.py`) builds a `NodeSpec`
   from the node's `inputs`/`metadata` and hands off to
   `ComputerUseSkill.run()`. The returned `AgentResult` is identical in shape
   to what the orchestrator already receives from `browser` and
   `sandbox_executor`. `flow.py` is untouched and byte-identical to Session 9.

---

## Running the Agent

### Option A — direct task runner (recommended for demo/recording)

```powershell
# Terminal 1: boot the gateway (needed for the paint task only)
cd "C:\The School Of AI\Session 10 - Computer Use Agent\llm_gatewayV9"
uv run main.py

# Terminal 2: run a task
cd "C:\The School Of AI\Session 10 - Computer Use Agent\S10code"
uv run python run_task.py calculator --expr "12.5*8+100="
uv run python run_task.py electron --content "Hello from the computer-use agent."
uv run python run_task.py paint
```

> **Electron app prerequisite:** before running the `electron` task for the
> first time, install its dependency once:
> ```powershell
> cd "C:\The School Of AI\Session 10 - Computer Use Agent\S10code\electron_app"
> npm install
> ```
> Requires Node.js + npm. `node_modules/` is gitignored, so a fresh clone must
> run `npm install` before the task will launch.

Set `CU_SLOWMO_MS=300` for a followable recording:
```powershell
$env:CU_SLOWMO_MS = "300"
uv run python run_task.py calculator --expr "12.5*8+100="
```

### Option B — orchestrator path (proves catalog membership)

```powershell
# Terminal 1: gateway running (same as above)
# Terminal 2:
cd "C:\The School Of AI\Session 10 - Computer Use Agent\S10code"
uv run python flow.py "Use the computer to compute 12.5*8+100 with Windows Calculator"
```

The Planner emits a `computer_use` node; `skills.py` dispatches it; the
orchestrator receives the `AgentResult` — no orchestrator code was changed.

---

## Trajectory Evidence

Every run writes artifacts under:

```
S10code/state/sessions/<session-id>/computer_use/<task>_<n>/
```

For the direct runner the session id is `direct`:

```
S10code/state/sessions/direct/computer_use/calculator_1/
  step_01.json
  step_02.json
  trajectory.json

S10code/state/sessions/direct/computer_use/paint_1/
  step_01.json
  step_01_screen.png          # raw screenshot (coordinate-based vision; no set-of-marks)
  trajectory.json
  # step_NN_marked.png is written only when a marked image is supplied
  # (the recorder supports it; the current VisionDriver does not emit one)
```

`trajectory.json` is the primary submission artifact: it contains the
ordered step log, layer counts, vision call count, escalation notes, and
the final result string.

---

## Module Layout

```
S10code/
  computer_use/
    __init__.py
    skill.py          # ComputerUseSkill — cascade wrapper + per-task entry
    controllers.py    # LiveDesktop (pyautogui/pywinauto/mss) + pure helpers
    drivers.py        # AXTextDriver, VisionDriver — bounded step loops
    recorder.py       # TrajectoryRecorder + start_recording
  prompts/
    computer_use.md   # skill prompt (cascade contract + driver system text)
  run_task.py         # thin single-task runner (demo/recording)
  agent_config.yaml   # +computer_use: block
  skills.py           # +computer_use dispatch branch
  schemas.py          # +ComputerUseOutput (additive)
```

Reused without modification: `llm_gatewayV9/`, `flow.py`, `recovery.py`,
`persistence.py`, `browser/client.py` (`V9Client`).
