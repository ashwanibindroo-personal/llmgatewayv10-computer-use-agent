import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from computer_use.drivers import AXTextDriver, VisionDriver, DriverConfig


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
        return b"PNG"

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


def test_vision_driver_clicks_then_done_and_counts_vision():
    client = FakeClient(['{"action":"click","x":10,"y":20}',
                         '{"action":"done","result":"drawn"}'])
    desktop = FakeDesktop()
    cfg = DriverConfig(goal="click target", max_steps=5)
    res = asyncio.run(VisionDriver(desktop, client, cfg).run())
    assert res.success and res.result == "drawn"
    assert desktop.clicked == [(10, 20)]
    assert client.vision_calls == 2  # one per turn


def test_driver_gives_up_after_max_steps():
    client = FakeClient(['{"action":"invoke","name":"Seven"}'] * 10)
    cfg = DriverConfig(goal="never done", max_steps=3)
    res = asyncio.run(AXTextDriver(FakeDesktop(), client, cfg, title_re="Calc").run())
    assert not res.success
    assert res.turns == 3
