import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from computer_use.controllers import (
    build_calculator_keys, serialize_ax_legend, parse_action,
)


def test_build_calculator_keys_basic():
    assert build_calculator_keys("12.5*8+100=") == [
        "1", "2", ".", "5", "multiply", "8", "add", "1", "0", "0", "enter",
    ]


def test_build_calculator_keys_rejects_unknown_char():
    with pytest.raises(ValueError):
        build_calculator_keys("2^3")


def test_serialize_ax_legend_numbers_controls():
    legend, idx = serialize_ax_legend([
        {"name": "Seven", "control_type": "Button"},
        {"name": "Plus", "control_type": "Button", "value": "+"},
    ])
    assert "[1] Button \"Seven\"" in legend
    assert "[2] Button \"Plus\"" in legend
    assert idx[2]["name"] == "Plus"


def test_parse_action_strips_fences():
    assert parse_action('```json\n{"action": "click", "mark": 3}\n```') == {
        "action": "click", "mark": 3,
    }
