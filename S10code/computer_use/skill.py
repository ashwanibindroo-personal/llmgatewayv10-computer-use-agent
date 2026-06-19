"""Session 10: the ComputerUse skill — cascade wrapper around the desktop
controllers and drivers. Same role browser/skill.py plays for the web:
translate NodeSpec → AgentResult and own the layer cascade.

Per-task cascade (cheapest viable layer first; escalate on insufficiency):
  * calculator → Layer 1 hotkeys (zero LLM, zero vision); if clipboard
    read returns empty the run fails cleanly (ax_llm is a documented
    extension point, not implemented).
  * electron   → bundled Electron app via CDP 'page' layer over the debug port.
  * paint      → forced vision layer (canvas has no AX labels).
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


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    """Poll until a TCP port accepts a connection, or timeout. Replaces a
    fixed sleep so we attach as soon as the CDP endpoint is live."""
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


async def _await_renderer_page(browser, timeout: float = 20.0):
    """Wait for the Electron app's renderer page to appear over CDP. Right
    after launch `contexts[].pages` can be empty for a moment, so poll across
    every context and prefer the app window (index.html); fall back to any
    page once one exists."""
    import asyncio

    deadline = time.time() + timeout
    while time.time() < deadline:
        pages = [pg for c in browser.contexts for pg in c.pages]
        app_pg = next((pg for pg in pages if "index.html" in pg.url), None)
        if app_pg is not None:
            return app_pg
        if pages:
            return pages[0]
        await asyncio.sleep(0.5)
    return None


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
            if task == "electron":
                return await self._electron(node, rec, t0)
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

    # ── calculator: hotkeys (zero LLM, zero vision); fail cleanly if empty ──
    def _calculator(self, node, rec, t0) -> AgentResult:
        expr = node.metadata.get("expression", "1+1=")
        goal = node.metadata.get("goal", f"compute {expr}")
        result = self._calc_hotkeys(goal, expr, rec)
        if result:
            rec.stop(result=result)
            return self._pack("calculator", "hotkeys", rec, result,
                              time.time() - t0)
        # Hotkeys produced no readable result — fail cleanly.
        rec.note("tried hotkeys → no clipboard result → failing "
                 "(ax_llm fallback is a documented extension point, not implemented)")
        return self._err("calculator", "interaction_failed",
                         "hotkeys produced no result", time.time() - t0, rec=rec,
                         path="hotkeys")

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
        return result or None

    # ── electron: bundled Electron app, CDP 'page' layer ─────────────────────
    async def _electron(self, node, rec, t0) -> AgentResult:
        res = await self._run_electron(node.metadata.get("goal", "edit a file"),
                                       node.metadata, rec)
        rec.stop(result=res.result)
        if res.success:
            return self._pack("electron", "electron", rec, res.result,
                              time.time() - t0, turns=res.turns)
        return self._err("electron", "interaction_failed", res.note,
                         time.time() - t0, path="electron")

    async def _run_electron(self, goal: str, meta: dict, rec) -> DriverResult:
        """Live: launch the bundled Electron app with --remote-debugging-port,
        attach over CDP, and drive its renderer with the page tool — type into
        the editor, read it back, and persist the text as a tangible artifact.

        We ship a tiny Electron app (electron_app/) rather than target VS Code:
        modern VS Code does not expose its renderer to CDP (the port opens but
        /json/list is empty), whereas an app we control reliably exposes its
        page — which is what this task exists to demonstrate."""
        import subprocess
        import tempfile
        from playwright.async_api import async_playwright

        content = meta.get("content", "Hello from the computer-use agent.")
        port = int(meta.get("port", 9222))
        app_dir = Path(__file__).resolve().parent.parent / "electron_app"
        electron_exe = (Path(meta["electron_exe"]) if meta.get("electron_exe")
                        else app_dir / "node_modules" / "electron" / "dist" / "electron.exe")
        if not electron_exe.is_file():
            raise ControllerUnavailable(
                f"Electron binary not found at {electron_exe}. "
                f"Run `npm install` in {app_dir}.")
        scratch = Path(tempfile.gettempdir()) / "s10_cu_scratch"
        scratch.mkdir(exist_ok=True)
        target = scratch / "electron_out.txt"

        # Launch detached with stdio to DEVNULL so the GUI child never holds the
        # caller's console/pipe (otherwise the runner can hang waiting for EOF).
        subprocess.Popen(
            [str(electron_exe), str(app_dir), f"--remote-debugging-port={port}"],
            shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
        # Poll the port (replaces a fixed sleep). 127.0.0.1 not "localhost":
        # localhost can resolve to IPv6 ::1 while Chromium binds IPv4 only.
        if not _wait_for_port("127.0.0.1", port, timeout=30.0):
            raise ControllerUnavailable(
                f"Electron remote-debugging port {port} did not open within 30s")
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            page = await _await_renderer_page(browser, timeout=20.0)
            if page is None:
                await browser.close()
                raise ControllerUnavailable(
                    "connected to Electron CDP but no renderer page appeared")
            rec.step("electron", "connect_cdp", f"port {port}")
            # Drive the renderer through the page tool: type into the editor,
            # then read the value straight back from the DOM to verify.
            await page.fill("#editor", content)
            rec.step("electron", "type_content", "#editor")
            typed = await page.input_value("#editor")
            await page.evaluate(
                "document.getElementById('status').textContent = 'typed by agent'")
            ok = typed == content
            target.write_text(typed, encoding="utf-8")  # tangible artifact
            rec.step("electron", "verify_and_write", str(target),
                     outcome="ok" if ok else f"mismatch (got {len(typed)} chars)")
            try:
                await page.close()                       # close window → app quits
            except Exception:                            # noqa: BLE001
                pass
            await browser.close()
        return DriverResult(ok, 2,
                            f"typed+verified in Electron renderer; wrote {target}"
                            if ok else None,
                            "" if ok else "renderer value mismatch")

    # ── paint: forced vision layer (last resort) ────────────────────────────
    async def _paint(self, node, rec, t0) -> AgentResult:
        res = await self._run_vision(node.metadata.get("goal",
                "Open a blank canvas in MS Paint and draw a circle in the centre"),
                rec)
        rec.stop(result=res.result)
        if res.success:
            return self._pack("paint", "vision", rec, res.result,
                              time.time() - t0, turns=res.turns)
        return self._err("paint", "interaction_failed", res.note,
                         time.time() - t0, path="vision")

    async def _run_vision(self, goal: str, rec) -> DriverResult:
        """Live: open MS Paint, then drive the label-less canvas with the
        vision driver (raw screenshot + coordinate-based vision; no set-of-marks)."""
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
            actions=rec.steps,
        )
        return AgentResult(success=True, agent_name=self.NAME,
                           output=out.model_dump(), elapsed_s=elapsed)

    def _err(self, task, code, msg, elapsed, *, rec=None,
             path: str = "hotkeys") -> AgentResult:
        if rec is not None:
            rec.stop(result=None)
        out = ComputerUseOutput(task=task or "unknown", path=path,
                                vision_calls=getattr(rec, "vision_calls", 0)
                                if rec else 0)
        return AgentResult(success=False, agent_name=self.NAME,
                           output=out.model_dump(), error=msg, error_code=code,
                           elapsed_s=elapsed)
