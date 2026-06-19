import sys
from pathlib import Path

# When running via pytest the cwd is the tests/ dir; the recovery module
# sits one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import ComputerUseOutput


def test_computer_use_output_roundtrip():
    out = ComputerUseOutput(
        task="calculator", path="hotkeys", turns=3, result="1100",
        actions=[{"layer": "hotkeys", "keys": "12.5*8+100"}],
        trajectory_dir="state/sessions/s/computer_use/calculator_1",
        vision_calls=0,
    )
    d = out.model_dump()
    assert d["task"] == "calculator"
    assert d["path"] == "hotkeys"
    assert d["vision_calls"] == 0
    assert ComputerUseOutput.model_validate(d).result == "1100"


def test_path_must_be_known_layer():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ComputerUseOutput(task="x", path="telepathy")
