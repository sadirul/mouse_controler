"""Empty Recycle Bin action: must always go through a confirmation, never delete directly."""
from __future__ import annotations

from app import recycle_bin
from app.gesture_state import Ev, Event
from app.settings_manager import WINDOW_ACTIONS
from tests.conftest import Sim, default_config


def _sim(items: int):
    cfg = default_config()
    cfg["gestures"]["mappings"]["horns_hold"] = "empty_recycle_bin"
    sim = Sim(cfg)
    sim.controller.bin_query = lambda: (items, 2048 * items)
    return sim


def _fire(sim: Sim):
    sim.controller._execute(Event(Ev.WINDOW_COMMAND, {"action": "empty_recycle_bin", "trigger": "horns_hold", "dialog": False}))


def test_action_is_available():
    assert "empty_recycle_bin" in WINDOW_ACTIONS


def test_gesture_asks_for_confirmation(monkeypatch):
    monkeypatch.setattr(recycle_bin, "empty", lambda: (_ for _ in ()).throw(AssertionError("must not empty directly")))
    sim = _sim(5)
    _fire(sim)
    assert ("confirm_empty_bin", {"items": 5, "bytes": 10240}) in sim.notices
    assert sim.windows.calls == [] if hasattr(sim.windows, "calls") else True


def test_already_empty_bin_needs_no_dialog():
    sim = _sim(0)
    _fire(sim)
    kinds = [k for k, _ in sim.notices]
    assert "recycle_bin_empty" in kinds and "confirm_empty_bin" not in kinds


def test_horns_mapped_to_bin_triggers_request():
    sim = _sim(3)
    sim.hold("horns", 1200)
    assert any(k == "confirm_empty_bin" for k, _ in sim.notices)


def test_human_size():
    assert recycle_bin.human_size(500) == "500 bytes"
    assert recycle_bin.human_size(1536) == "1.5 KB"
    assert recycle_bin.human_size(3 * 1024 ** 3) == "3.0 GB"
