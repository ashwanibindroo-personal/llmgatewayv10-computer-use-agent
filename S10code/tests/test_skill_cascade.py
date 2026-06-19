import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from computer_use.skill import ComputerUseSkill
from computer_use.drivers import DriverResult
from schemas import NodeSpec


def _skill(tmp_path):
    return ComputerUseSkill(artifacts_root=str(tmp_path), session="t")


def test_calculator_uses_hotkeys_zero_vision(tmp_path, monkeypatch):
    sk = _skill(tmp_path)
    monkeypatch.setattr(sk, "_calc_hotkeys", lambda goal, expr, rec: "1100")
    node = NodeSpec(skill="computer_use",
                    metadata={"task": "calculator", "expression": "12.5*8+100="})
    res = asyncio.run(sk.run(node))
    assert res.success
    assert res.output["path"] == "hotkeys"
    assert res.output["result"] == "1100"
    assert res.output["vision_calls"] == 0


def test_canvas_uses_vision_path(tmp_path, monkeypatch):
    sk = _skill(tmp_path)
    async def fake_vision(goal, rec):
        rec.step("vision", "click", "target", vision_called=True)
        return DriverResult(True, 2, "hit")
    monkeypatch.setattr(sk, "_run_vision", fake_vision)
    node = NodeSpec(skill="computer_use", metadata={"task": "canvas"})
    res = asyncio.run(sk.run(node))
    assert res.success and res.output["path"] == "vision"
    assert res.output["vision_calls"] == 1


def test_electron_uses_electron_path(tmp_path, monkeypatch):
    sk = _skill(tmp_path)
    async def fake_electron(goal, meta, rec):
        rec.step("electron", "type_content", "#editor")
        return DriverResult(True, 1, "typed")
    monkeypatch.setattr(sk, "_run_electron", fake_electron)
    node = NodeSpec(skill="computer_use",
                    metadata={"task": "electron", "content": "hello"})
    res = asyncio.run(sk.run(node))
    assert res.success and res.output["path"] == "electron"
    assert res.output["vision_calls"] == 0


def test_unknown_task_fails_cleanly(tmp_path):
    sk = _skill(tmp_path)
    res = asyncio.run(sk.run(NodeSpec(skill="computer_use", metadata={"task": "fly"})))
    assert not res.success and res.error_code == "interaction_failed"


def test_controller_unavailable_maps_to_error_code(tmp_path, monkeypatch):
    from computer_use.controllers import ControllerUnavailable
    sk = _skill(tmp_path)
    def boom(goal, expr, rec):
        raise ControllerUnavailable("Calculator window not found")
    monkeypatch.setattr(sk, "_calc_hotkeys", boom)
    node = NodeSpec(skill="computer_use",
                    metadata={"task": "calculator", "expression": "1+1="})
    res = asyncio.run(sk.run(node))
    assert not res.success
    assert res.error_code == "controller_unavailable"
