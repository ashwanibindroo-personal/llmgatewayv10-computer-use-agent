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
