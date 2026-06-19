"""Demo-mode launch options: BROWSER_HEADFUL / BROWSER_SLOWMO_MS env vars."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from browser.skill import _launch_options


def test_default_is_headless_new_headless_channel(monkeypatch):
    # channel="chromium" = Playwright's NEW headless mode: real-Chrome network
    # fingerprint, which huggingface.co's edge doesn't reset (old headless
    # shell intermittently got net::ERR_CONNECTION_RESET).
    monkeypatch.delenv("BROWSER_HEADFUL", raising=False)
    monkeypatch.delenv("BROWSER_SLOWMO_MS", raising=False)
    assert _launch_options() == {"headless": True, "channel": "chromium"}


def test_headful_with_slowmo(monkeypatch):
    monkeypatch.setenv("BROWSER_HEADFUL", "1")
    monkeypatch.setenv("BROWSER_SLOWMO_MS", "400")
    assert _launch_options() == {"headless": False, "slow_mo": 400}


def test_garbage_slowmo_ignored(monkeypatch):
    monkeypatch.setenv("BROWSER_HEADFUL", "0")
    monkeypatch.setenv("BROWSER_SLOWMO_MS", "fast")
    assert _launch_options() == {"headless": True, "channel": "chromium"}
