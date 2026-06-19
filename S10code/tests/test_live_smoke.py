import asyncio
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_task import build_node
from computer_use.skill import ComputerUseSkill


pytestmark = pytest.mark.live


def _run(node):
    sk = ComputerUseSkill(artifacts_root="state/sessions/smoke/computer_use",
                          session="smoke", slowmo_ms=300)
    return asyncio.run(sk.run(node))


def test_calculator_live_zero_vision():
    res = _run(build_node("calculator", expr="12.5*8+100="))
    assert res.success, res.error
    assert res.output["path"] == "hotkeys"
    assert res.output["vision_calls"] == 0
    assert "1100" in (res.output["result"] or "")


def test_electron_live():
    res = _run(build_node("electron", content="hello from S10"))
    assert res.success, res.error
    assert res.output["path"] == "electron"


def test_paint_live_vision():
    res = _run(build_node("paint"))
    assert res.success, res.error
    assert res.output["path"] == "vision"
    assert res.output["vision_calls"] >= 1
