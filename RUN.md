# RUN.md — running the Session 10 computer-use agent

Windows 11 + PowerShell. You need **two terminals**: one for the gateway
(leave it running), one for the agent.

## Prerequisites

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- VS Code installed and launchable as `code` from PowerShell (needed for the
  `vscode` task).
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

Expect `Uvicorn running on http://0.0.0.0:8109`. The `vscode` and `paint`
tasks call this gateway for every LLM/vision request. The `calculator` task
does not call the gateway at all (hotkeys only).

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

## Step 4 — Run the VS Code task (Terminal 2)

VS Code must be launchable as `code` from PowerShell. Verify first:
```powershell
code --version
```

Then run:
```powershell
uv run python run_task.py vscode --content "Hello from the computer-use agent."
```

What happens:
- VS Code launches with `--remote-debugging-port=9222` pointing at a temp
  scratch folder (`%TEMP%\s10_cu_scratch`).
- Playwright connects over CDP, opens a new file, types the content, saves it
  as `scratch.txt` via Save As.
- `vision_calls=0` confirms the Electron CDP layer needs no screenshots.
- Trajectory written to:
  `state\sessions\direct\computer_use\vscode_1\`

> Allow ~8 seconds for VS Code to start before Playwright connects. If the
> run fails with a connection error, VS Code may be slow on this machine —
> the `time.sleep(6.0)` in the driver can be raised in `skill.py`.

## Step 5 — Run the MS Paint task (Terminal 2, gateway must be running)

```powershell
uv run python run_task.py paint
```

What happens:
- MS Paint opens (`mspaint.exe`).
- The vision driver takes a full-screen screenshot each turn, sends it to
  the gateway `/v1/vision`, and acts on the returned pixel coordinates
  (click or drag). The default goal is `"Open a blank canvas in MS Paint and
  draw a circle in the centre"`.
- `vision_calls > 0` confirms the vision constraint.
- Screenshots saved as `step_NN_screen.png` in the trajectory directory.
- Trajectory written to:
  `state\sessions\direct\computer_use\paint_1\`

A custom goal can be set with `--goal`:
```powershell
uv run python run_task.py paint --goal "Draw a red square in the top-left corner"
```

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
- `vision_calls` — total vision API calls (0 for calculator and vscode).
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
- **Vision task step cap:** `VisionDriver` is bounded to 8 steps by default
  (`max_steps=8` in `skill.py`). If the vision LLM gets stuck, the run stops
  after 8 turns and returns `success=False`.
- **Live tasks move the real mouse and keyboard.** Do not click or type while
  a task is running.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Gateway not running — paint/vscode fail with `ConnectionRefusedError` | Start Terminal 1 (`uv run main.py`) before running paint or vscode |
| `ANTHROPIC_API_KEY` not found | Add it to `llm_gatewayV9\.env` |
| VS Code connection refused on CDP port | VS Code took >6 s to start; raise `time.sleep(6.0)` in `skill.py` `_run_electron` |
| `code: command not found` | Add VS Code to PATH, or install it; verify with `code --version` |
| `ControllerUnavailable: window 'Calculator'` | Calculator window did not focus in time; increase `time.sleep(1.5)` in `_calc_hotkeys` |
| pyautogui `FailSafeException` | Mouse hit a corner (intentional abort); re-run |
| Vision task loops without `done` | Vision LLM returned unexpected JSON; run will stop at the step cap |
| `WinError 5: Access is denied` writing state files | Defender scanning mid-rename → admin PowerShell: `Add-MpPreference -ExclusionPath "<repo path>"` |
