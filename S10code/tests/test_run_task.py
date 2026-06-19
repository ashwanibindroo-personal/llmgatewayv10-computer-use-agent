import sys
from pathlib import Path

# When running via pytest the cwd is the tests/ dir; run_task sits one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_task import build_node


def test_build_node_calculator_defaults():
    node = build_node("calculator", expr="12.5*8+100=")
    assert node.skill == "computer_use"
    assert node.metadata["task"] == "calculator"
    assert node.metadata["expression"] == "12.5*8+100="


def test_build_node_electron_content():
    node = build_node("electron", content="hi there")
    assert node.metadata["task"] == "electron"
    assert node.metadata["content"] == "hi there"


def test_build_node_canvas():
    node = build_node("canvas")
    assert node.metadata["task"] == "canvas"
