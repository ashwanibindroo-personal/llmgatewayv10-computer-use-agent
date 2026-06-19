# Session 10 — Computer-Use Agent

A **`computer_use`** skill added to the Session 9 DAG skill catalog that
automates the **local Windows 11 machine** through a cost-laddered cascade,
completing three desktop tasks and producing trajectory evidence of cascade
discipline.

**Demo video:** https://youtu.be/trRrAzsE3lw

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
| **Canvas** — a label-less HTML canvas (`S10code/vision_canvas/target.html`) opened in a browser app window; the agent set-of-marks-locates the red circle and clicks it (turns green/HIT) | **vision** (last resort — screenshot + set-of-marks) | **vision (≥1 vision call)** |

### Constraint coverage (explicit)

- **≥1 vision call** — Canvas task; each turn the `VisionDriver` takes a
  screenshot, overlays a numbered yellow mark grid via `controllers.annotate_grid()`
  (set-of-marks), sends the annotated image to `/v1/vision`, the model returns a
  mark number (not raw pixels), and the agent clicks that mark's pixel coordinate;
  `trajectory.json` records `vision_calls > 0`.
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
Layer 4  — vision            mss screenshot → V9Client.vision (set-of-marks: numbered grid → mark number)
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

## Challenges & Engineering Decisions

The cascade philosophy held throughout: each task settles at the cheapest layer
that actually works **on this OS**, and where a platform reality blocked a
layer, we adapted the *approach* rather than the discipline. The notable ones:

1. **VS Code's renderer isn't exposed to CDP.** The Electron task originally
   targeted VS Code via `--remote-debugging-port`. On modern VS Code the port
   opens but `/json/list` returns **zero page targets** — `connect_over_cdp`
   succeeds with nothing to drive. Rather than fight a version-specific quirk,
   we ship a **bundled minimal Electron app** (`electron_app/`) we control,
   which reliably exposes its renderer and demonstrates the identical
   debug-port + page-tool mechanism.
2. **`pyautogui` can't draw in Windows 11 Paint.** The vision task first drew
   in MS Paint, but synthetic drags leave no stroke on the WinUI Paint canvas.
   We pivoted to a **self-contained label-less HTML canvas**
   (`vision_canvas/target.html`) where clicks register reliably and success is
   visually verifiable (the target turns green / "HIT").
3. **VLMs are imprecise at raw pixel coordinates.** Asked for exact click
   coordinates, the vision model was ~200+px off and missed repeatedly. Fixed
   with **set-of-marks**: overlay a numbered grid (`controllers.annotate_grid`),
   have the model return a **mark number** (coarse spatial reasoning it does
   well), and map the mark back to exact pixels.
4. **Small models won't reliably emit JSON-only.** The model returned prose and
   malformed pseudo-tool-call blocks instead of clean actions. Both drivers now
   force **structured output** via the gateway's JSON-schema mode, so each turn
   yields a single validated action object.
5. **Windows Calculator is single-instance.** Relaunching `calc.exe` refocuses
   a window with stale state, and `pywinauto` errored on **multiple matching
   "Calculator" windows**. Fixed by pressing `Esc` to clear before typing and
   by picking the first *visible* matching window instead of erroring on
   ambiguity.
6. **Reliable launches.** Electron's binary download can be skipped by `npm`
   when it reports "up to date" (fallback documented in RUN.md), and GUI
   subprocesses are launched with detached stdio so the runner never hangs
   waiting on an inherited console pipe.

Each fix is reflected in the trajectory evidence (e.g. the canvas
`step_NN_marked.png` files show the set-of-marks grid the model actually chose
from).

---

## Running the Agent

### Option A — direct task runner (recommended for demo/recording)

```powershell
# Terminal 1: boot the gateway (needed for the canvas task only)
cd "C:\The School Of AI\Session 10 - Computer Use Agent\llm_gatewayV9"
uv run main.py

# Terminal 2: run a task
cd "C:\The School Of AI\Session 10 - Computer Use Agent\S10code"
uv run python run_task.py calculator --expr "12.5*8+100="
uv run python run_task.py electron --content "Hello from the computer-use agent."
uv run python run_task.py canvas
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

S10code/state/sessions/direct/computer_use/canvas_1/
  step_01.json
  step_01_screen.png          # raw screenshot (every vision turn)
  step_01_marked.png          # numbered set-of-marks grid overlay (every vision turn)
  trajectory.json
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
  electron_app/       # bundled minimal Electron app (debug-port task)
    main.js, index.html, package.json   # run `npm install` once; node_modules gitignored
  vision_canvas/
    target.html       # label-less HTML canvas target (set-of-marks vision task)
  run_task.py         # thin single-task runner (demo/recording)
  agent_config.yaml   # +computer_use: block
  skills.py           # +computer_use dispatch branch
  schemas.py          # +ComputerUseOutput (additive)
```

Reused without modification: `llm_gatewayV9/`, `flow.py`, `recovery.py`,
`persistence.py`, `browser/client.py` (`V9Client`).
