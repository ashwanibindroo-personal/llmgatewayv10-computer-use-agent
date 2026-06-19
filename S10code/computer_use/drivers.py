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
