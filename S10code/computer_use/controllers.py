"""Session 10: Windows OS controllers for the computer-use cascade.

Two halves:
  * Pure helpers (key-token building, AX-legend serialisation, action
    parsing) — deterministic, unit-tested, no machine access.
  * LiveDesktop — thin wrappers over pyautogui / pywinauto / mss that
    actually drive the machine. Not unit-tested (they move the real
    mouse/keyboard); exercised by the Task 9 live smoke runner.
"""
from __future__ import annotations

import json
import time

_OP_TOKENS = {"+": "add", "-": "subtract", "*": "multiply", "/": "divide", "=": "enter"}


def build_calculator_keys(expression: str) -> list[str]:
    """Map an arithmetic expression to pyautogui key tokens for Windows
    Calculator. Digits and '.' map to themselves; operators map to the
    calc app's named keys. Unsupported characters raise ValueError so a
    bad expression fails loudly instead of typing garbage."""
    tokens: list[str] = []
    for ch in expression.replace(" ", ""):
        if ch.isdigit() or ch == ".":
            tokens.append(ch)
        elif ch in _OP_TOKENS:
            tokens.append(_OP_TOKENS[ch])
        else:
            raise ValueError(f"unsupported character in expression: {ch!r}")
    return tokens


def serialize_ax_legend(controls: list[dict]) -> tuple[str, dict[int, dict]]:
    """Number a flat list of AX controls into a legend string + index map.
    Cheap text the Layer-2b LLM reads instead of an image."""
    lines, idx = [], {}
    for i, c in enumerate(controls, start=1):
        name = c.get("name", "")
        ctype = c.get("control_type", "Control")
        val = c.get("value")
        line = f'[{i}] {ctype} "{name}"'
        if val:
            line += f" = {val!r}"
        lines.append(line)
        idx[i] = c
    return "\n".join(lines), idx


def parse_action(text: str) -> dict:
    """Parse a single JSON action object from LLM text (fence-tolerant)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[:-3]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except json.JSONDecodeError:
                pass
    return {}


class ControllerUnavailable(RuntimeError):
    """A required OS controller or target app could not be reached."""


class LiveDesktop:
    """Thin live wrappers. Imports happen lazily so the pure helpers above
    (and their tests) never require a desktop session."""

    def __init__(self, slowmo_ms: int = 0):
        self.slowmo_ms = slowmo_ms

    def _pause(self):
        if self.slowmo_ms:
            time.sleep(self.slowmo_ms / 1000.0)

    def type_keys(self, tokens: list[str]) -> None:
        import pyautogui
        for tok in tokens:
            pyautogui.press(tok) if len(tok) > 1 or tok.isalpha() else pyautogui.typewrite(tok)
            self._pause()

    def read_clipboard(self) -> str:
        import pyperclip
        return pyperclip.paste()

    def hotkey(self, *keys: str) -> None:
        import pyautogui
        pyautogui.hotkey(*keys)
        self._pause()

    def screenshot(self) -> bytes:
        import io
        import mss
        from PIL import Image
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])
            img = Image.frombytes("RGB", shot.size, shot.rgb)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def click(self, x: int, y: int) -> None:
        import pyautogui
        pyautogui.click(x, y)
        self._pause()

    def drag(self, path: list[tuple[int, int]]) -> None:
        import pyautogui
        if not path:
            return
        pyautogui.moveTo(*path[0])
        pyautogui.mouseDown()
        for x, y in path[1:]:
            pyautogui.moveTo(x, y, duration=0.05)
        pyautogui.mouseUp()
        self._pause()

    def focus_window(self, title_re: str):
        from pywinauto import Desktop
        try:
            win = Desktop(backend="uia").window(title_re=title_re)
            win.set_focus()
            return win
        except Exception as e:  # noqa: BLE001
            raise ControllerUnavailable(f"window {title_re!r}: {e}") from e

    def ax_controls(self, title_re: str) -> list[dict]:
        win = self.focus_window(title_re)
        out = []
        for c in win.descendants():
            try:
                out.append({"name": c.window_text(),
                            "control_type": c.element_info.control_type})
            except Exception:  # noqa: BLE001
                continue
        return out

    def invoke_control(self, title_re: str, name: str) -> bool:
        win = self.focus_window(title_re)
        try:
            win.child_window(title=name, control_type="Button").invoke()
            self._pause()
            return True
        except Exception:  # noqa: BLE001
            return False
