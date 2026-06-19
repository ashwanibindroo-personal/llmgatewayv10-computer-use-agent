# RUN.md — running the Session 10 computer-use agent

Windows 11 + PowerShell. You need **two terminals**: one for the gateway
(leave it running), one for the agent.

## Prerequisites

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- Node.js + npm (needed for the `electron` task). One-time setup:
  ```powershell
  cd "C:\The School Of AI\Session 10 - Computer Use Agent\S10code\electron_app"
  npm install
  ```
  This installs Electron locally. `node_modules/` is gitignored, so a fresh
  clone must run `npm install` before the task will launch. If `npm install`
  reports "up to date" but the task still says *Electron binary not found*
  (the binary-download step was skipped), fetch it directly:
  ```powershell
  node node_modules/electron/install.js
  ```
- Gateway `.env` with your Anthropic key (not committed):
  - `llm_gatewayV9\.env` — needs `ANTHROPIC_API_KEY` and
    `ANTHROPIC_MODEL=claude-haiku-4-5-20251001`
- One-time, first run only:
  ```powershell
  cd llm_gatewayV9 ; uv sync
  cd ..\S10code    ; uv sync ; uv run playwright install chromium
  ```
  The new S10 dependencies (`pyautogui`, `pyperclip`, `pywinauto`, `mss`)
  are declared in `S10code/pyproject.toml` and installed by `uv sync`.

## Step 1 — Boot the gateway (Terminal 1, leave running)

```powershell
cd "C:\The School Of AI\Session 10 - Computer Use Agent\llm_gatewayV9"
uv run main.py
```

Expect `Uvicorn running on http://0.0.0.0:8109`. Only the `canvas` task calls
this gateway (for vision requests). The `calculator` and `electron` tasks do
not call the gateway at all (hotkeys/clipboard and CDP only, respectively).

**Restart the gateway after any change to `agent_routing.yaml`, `router.py`,
`providers.py`, `main.py`, or `pricing.py`** — those load once at startup.

## Step 2 — Set up the recording environment (Terminal 2)

```powershell
cd "C:\The School Of AI\Session 10 - Computer Use Agent\S10code"
$env:CU_SLOWMO_MS    = "300"    # 0.3s between OS actions — followable on screen
$env:PYTHONUNBUFFERED = "1"     # logs appear immediately
```

These env vars live only in the current terminal session. Set them in the
**same** window you run `run_task.py` from.

`CU_SLOWMO_MS` inserts a pause after every `pyautogui` action (hotkey, click,
drag, type). 300 ms is comfortable for screen recording; raise to 500 for
slower recordings, set to 0 (or leave unset) for unthrottled runs.

## Step 3 — Run the Calculator task (Terminal 2)

```powershell
uv run python run_task.py calculator --expr "12.5*8+100="
```

What happens:
- Windows Calculator opens (`calc.exe`).
- The hotkeys driver types the expression character-by-character using
  pyautogui key names, then copies the result via `Ctrl+C`.
- The clipboard value is printed: `result='200'`.
- `vision_calls=0` confirms the zero-vision constraint.
- Trajectory written to:
  `state\sessions\direct\computer_use\calculator_1\`

## Step 4 — Run the Electron app task (Terminal 2)

Ensure `npm install` has been run in `S10code/electron_app/` (one-time — see
Prerequisites).

```powershell
uv run python run_task.py electron --content "Hello from the computer-use agent."
```

What happens:
- The bundled minimal Electron app (`S10code/electron_app/`) launches with
  `--remote-debugging-port=9222`; a temp working directory (`%TEMP%\s10_cu_scratch`)
  is used for output.
- Playwright connects over CDP via `connect_over_cdp` and drives the renderer
  page using the page tool: it types the content into the `#editor` textarea,
  reads the value back to verify it, then writes the text to
  `%TEMP%\s10_cu_scratch\electron_out.txt` as the tangible artifact.
- `vision_calls=0` confirms the Electron CDP layer needs no screenshots.
- Trajectory written to:
  `state\sessions\direct\computer_use\electron_1\`

## Step 5 — Run the Canvas (vision / set-of-marks) task (Terminal 2, gateway must be running)

```powershell
uv run python run_task.py canvas
```

What happens:
- A browser app window opens the bundled HTML canvas (`S10code/vision_canvas/target.html`)
  in Edge or Chrome via `--app=file://...` (falls back to the default browser). The page
  shows a red circle painted on a `<canvas>` element — pure pixels, no DOM/accessibility nodes.
- Each turn the vision driver takes a screenshot, overlays a numbered yellow mark grid
  (`controllers.annotate_grid()`), and sends the annotated image to the gateway `/v1/vision`.
  The model returns a mark number; the agent clicks that mark's pixel coordinate.
- The model picks the mark centred on the red circle, clicks it; the circle turns green
  and shows "HIT"; the model returns the done action.
- `vision_calls > 0` confirms the vision constraint.
- Both `step_NN_screen.png` (raw) and `step_NN_marked.png` (numbered grid overlay) are
  written every vision turn.
- Trajectory written to:
  `state\sessions\direct\computer_use\canvas_1\`

## Step 6 — Inspect the trajectory

```powershell
# List all runs for a task
Get-ChildItem "state\sessions\direct\computer_use\"

# Read the roll-up for the last calculator run
Get-Content "state\sessions\direct\computer_use\calculator_1\trajectory.json"
```

`trajectory.json` fields:
- `steps` — ordered per-step records (`layer`, `action`, `target`, `outcome`,
  `vision_called`).
- `notes` — escalation decisions (populated when the cascade escalates).
- `layer_counts` — `{layer_name: step_count}` summary.
- `vision_calls` — total vision API calls (0 for calculator and electron).
- `result` — the final result string returned by the skill.

Individual step files (`step_NN.json`) and screenshots (`step_NN_screen.png`)
sit alongside `trajectory.json` in the same directory.

## Step 7 (optional) — Run via the orchestrator

To prove `computer_use` is a real catalog member that the Planner can emit:

```powershell
# Terminal 1: gateway running
# Terminal 2:
cd "C:\The School Of AI\Session 10 - Computer Use Agent\S10code"
uv run python flow.py "Use the computer to compute 12.5*8+100 with Windows Calculator"
```

The orchestrator dispatches the `computer_use` node through the same
`skills.py` branch that `browser` and `sandbox_executor` use. `flow.py` is
byte-identical to Session 9.

## Safety notes

- **pyautogui failsafe:** slam the mouse to any screen corner to abort an
  in-flight run immediately. This is pyautogui's built-in failsafe and is
  always active.
- **Vision task step cap:** the canvas run is bounded to 6 steps
  (`max_steps=6` in `_run_vision` in `skill.py`). If the vision LLM gets stuck,
  the run stops after 6 turns and returns `success=False`.
- **Live tasks move the real mouse and keyboard.** Do not click or type while
  a task is running.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Gateway not running — canvas fails with `ConnectionRefusedError` | Start Terminal 1 (`uv run main.py`) before running canvas |
| `ANTHROPIC_API_KEY` not found | Add it to `llm_gatewayV9\.env` |
| Electron not found / CDP port didn't open | Run `npm install` in `S10code/electron_app/`; requires Node.js + npm |
| Electron connection refused on CDP port | The agent polls the debug port for up to 30 s (`_wait_for_port`); if it still times out, the Electron binary is likely missing — see the row above (`npm install` / `node node_modules/electron/install.js`) |
| `ControllerUnavailable: window 'Calculator'` | Usually a slow launch — the launch wait is `time.sleep(2.5)` in `_calc_hotkeys`; raise it if needed. Multiple matching Calculator windows are now handled automatically (first visible is picked) |
| pyautogui `FailSafeException` | Mouse hit a corner (intentional abort); re-run |
| Vision task loops without `done` | Vision LLM returned unexpected JSON; run will stop at the step cap |
| `WinError 5: Access is denied` writing state files | Defender scanning mid-rename → admin PowerShell: `Add-MpPreference -ExclusionPath "<repo path>"` |
