import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from computer_use.drivers import AXTextDriver, VisionDriver, DriverConfig


def _blank_png(w=400, h=400):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, "PNG")
    return buf.getvalue()


class FakeClient:
    def __init__(self, replies):
        self._replies = list(replies)
        self.chat_calls = 0
        self.vision_calls = 0

    async def chat(self, prompt, **kw):
        self.chat_calls += 1
        return _R(self._replies.pop(0))

    async def vision(self, image_data_url, prompt, **kw):
        self.vision_calls += 1
        return _R(self._replies.pop(0))


class _R:
    def __init__(self, text):
        self.text = text


class FakeDesktop:
    def __init__(self):
        self.invoked = []
        self.clicked = []

    def ax_controls(self, title_re):
        return [{"name": "Seven", "control_type": "Button"}]

    def invoke_control(self, title_re, name):
        self.invoked.append(name)
        return True

    def screenshot(self):
        # A real 400x400 PNG so annotate_grid (PIL) can mark it. With the
        # default grid (step=150, margin=60) marks form a 2x2 lattice at
        # x,y in {60, 210}; mark 4 is the bottom-right at (210, 210).
        return _blank_png(400, 400)

    def click(self, x, y):
        self.clicked.append((x, y))


def test_ax_text_driver_stops_on_done():
    client = FakeClient(['{"action":"invoke","name":"Seven"}',
                         '{"action":"done","result":"7"}'])
    desktop = FakeDesktop()
    cfg = DriverConfig(goal="press seven then done", max_steps=5)
    res = asyncio.run(AXTextDriver(desktop, client, cfg, title_re="Calc").run())
    assert res.success and res.result == "7"
    assert desktop.invoked == ["Seven"]
    assert client.vision_calls == 0


def test_vision_driver_set_of_marks_clicks_then_done():
    # Set-of-marks: the model picks mark 4, which the grid maps to (210,210).
    client = FakeClient(['{"action":"click","mark":4}',
                         '{"action":"done","result":"hit"}'])
    desktop = FakeDesktop()
    cfg = DriverConfig(goal="click the target", max_steps=5)
    res = asyncio.run(VisionDriver(desktop, client, cfg).run())
    assert res.success and res.result == "hit"
    assert desktop.clicked == [(210, 210)]
    assert client.vision_calls == 2  # one per turn


def test_driver_gives_up_after_max_steps():
    client = FakeClient(['{"action":"invoke","name":"Seven"}'] * 10)
    cfg = DriverConfig(goal="never done", max_steps=3)
    res = asyncio.run(AXTextDriver(FakeDesktop(), client, cfg, title_re="Calc").run())
    assert not res.success
    assert res.turns == 3
