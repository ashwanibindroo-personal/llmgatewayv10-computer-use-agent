import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import skills
from skills import SkillRegistry, run_skill


def test_registry_loads_computer_use():
    reg = SkillRegistry()
    assert "computer_use" in reg.names()


def test_run_skill_routes_to_computer_use(monkeypatch):
    reg = SkillRegistry()
    skill = reg.get("computer_use")

    captured = {}

    class FakeSkill:
        def __init__(self, **kw):
            captured["init"] = kw
        async def run(self, node):
            from schemas import AgentResult
            captured["task"] = node.metadata.get("task")
            return AgentResult(success=True, agent_name="computer_use",
                               output={"path": "hotkeys"})

    import computer_use.skill as cu
    monkeypatch.setattr(cu, "ComputerUseSkill", FakeSkill)

    graph_nodes = {"n:1": {"inputs": [], "metadata": {"task": "calculator"}}}
    result, _ = asyncio.run(run_skill(skill, "n:1", graph_nodes, "sess",
                                      "query", None))
    assert result.success
    assert captured["task"] == "calculator"
