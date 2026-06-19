"""Session 10: bounded per-layer driver loops for the computer-use cascade.

Shape mirrors browser/driver.py: a step loop with a step cap and a
consecutive-failure cap, writing per-turn evidence through the recorder.
AXTextDriver is the cheap interactive layer (text LLM, no image).
VisionDriver is the expensive last resort (one /v1/vision call per turn)."""
from __future__ import annotations

import base64
from dataclasses import dataclass

from .controllers import annotate_grid, parse_action, serialize_ax_legend


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
    "You drive a Windows desktop by looking at a screenshot that has a grid of "
    "numbered yellow MARKS overlaid on it. To act, pick the mark number that "
    "sits ON (or closest to the centre of) the thing you want to click and "
    'reply {"action":"click","mark":<number>}. When the goal is already '
    'achieved in the screenshot, reply {"action":"done","result":"<summary>"}. '
    "Use the mark numbers — never raw pixel coordinates. JSON only."
)

# Structured-output schemas. Small vision/text models (e.g. Haiku) do not
# reliably emit JSON-only when merely asked; forcing the schema makes the
# gateway return a single validated action object in GatewayResult.parsed.
_AX_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["invoke", "done"]},
        "name": {"type": "string"},
        "result": {"type": "string"},
    },
    "required": ["action"],
    "additionalProperties": False,
}

_VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["click", "done"]},
        "mark": {"type": "integer"},
        "result": {"type": "string"},
    },
    "required": ["action"],
    "additionalProperties": False,
}


def _action_from(reply):
    """Prefer the gateway's validated structured output; fall back to parsing
    the raw text (covers test fakes and providers without structured output)."""
    return getattr(reply, "parsed", None) or parse_action(reply.text)


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
            reply = await self.client.chat(prompt, system=_AX_SYS,
                                            schema=_AX_SCHEMA, schema_name="action",
                                            max_tokens=300)
            act = _action_from(reply)
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
        """Set-of-marks loop: overlay a numbered grid on each screenshot, let
        the model pick a mark, and click that mark's pixel. Robust to the VLM's
        weak raw-coordinate precision. Records both the raw and the marked
        screenshot per turn."""
        failures = 0
        for turn in range(1, self.cfg.max_steps + 1):
            png = self.d.screenshot()
            marked, marks = annotate_grid(png)
            data_url = "data:image/png;base64," + base64.b64encode(marked).decode()
            prompt = f"GOAL: {self.cfg.goal}"
            reply = await self.client.vision(data_url, prompt,
                                             system=_VISION_SYS,
                                             schema=_VISION_SCHEMA,
                                             schema_name="action", max_tokens=300)
            act = _action_from(reply)
            action = act.get("action")
            if action == "done":
                if self.cfg.recorder:
                    self.cfg.recorder.step(self.LAYER, "done",
                                           outcome=str(act.get("result")),
                                           screen_png=png, marked_png=marked,
                                           vision_called=True)
                return DriverResult(True, turn, str(act.get("result")), "done")
            mark = act.get("mark")
            if action == "click" and mark in marks:
                x, y = marks[mark]
                self.d.click(x, y)
                if self.cfg.recorder:
                    self.cfg.recorder.step(self.LAYER, "click",
                                           f"mark {mark} -> {x},{y}",
                                           screen_png=png, marked_png=marked,
                                           vision_called=True)
                failures = 0
            else:
                if self.cfg.recorder:
                    self.cfg.recorder.step(self.LAYER, "noop",
                                           outcome=f"unusable action: {act}",
                                           screen_png=png, marked_png=marked,
                                           vision_called=True)
                failures += 1
            if failures >= self.cfg.max_failures:
                return DriverResult(False, turn, None, "too many failures")
        return DriverResult(False, self.cfg.max_steps, None, "step cap")
