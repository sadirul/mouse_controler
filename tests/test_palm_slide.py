"""Open-hand slide -> flip to next / previous app (carousel)."""
from __future__ import annotations

from app.app_switcher import plan
from tests.conftest import Sim


def _cmds(sim: Sim) -> list[str]:
    return [c[1] for c in sim.windows.calls if c[0] == "command"]


def test_plan_is_a_carousel():
    stack = [1, 2, 3]
    assert plan(stack, 1, "next") == (2, 1)  # 1 goes to the back -> [2, 3, 1]
    assert plan([2, 3, 1], 2, "next") == (3, 2)  # -> [3, 1, 2]
    assert plan([3, 1, 2], 3, "previous") == (2, None)  # back to 2 -> [2, 3, 1]
    assert plan([2, 3, 1], 2, "previous") == (1, None)  # back to 1
    assert plan([5], 5, "next") == (None, None)


def test_slide_right_next_left_previous(sim: Sim):
    sim.hold("open_palm", 200, start=(0.3, 0.75))
    sim.hold("open_palm", 250, move=(0.35, 0), start=(0.3, 0.75))
    assert _cmds(sim) == ["next_app"]
    sim.hold("open_palm", 1200, start=(0.65, 0.75))  # rest (longer than the swing-back window)
    sim.hold("fist", 300)
    sim.hold("open_palm", 200, start=(0.65, 0.75))
    sim.hold("open_palm", 250, move=(-0.35, 0), start=(0.65, 0.75))
    assert _cmds(sim) == ["next_app", "previous_app"]


def test_swing_back_is_ignored(sim: Sim):
    sim.hold("open_palm", 200, start=(0.3, 0.75))
    sim.hold("open_palm", 250, move=(0.35, 0), start=(0.3, 0.75))
    sim.hold("open_palm", 250, move=(-0.35, 0), start=(0.65, 0.75))  # immediate return stroke
    assert _cmds(sim) == ["next_app"]


def test_repeated_slides_keep_flipping(sim: Sim):
    for _ in range(3):
        sim.hold("open_palm", 200, start=(0.3, 0.75))
        sim.hold("open_palm", 250, move=(0.35, 0), start=(0.3, 0.75))
        sim.hold("fist", 500)  # hand closes while moving back
    assert _cmds(sim) == ["next_app"] * 3


def test_slow_or_vertical_moves_do_nothing(sim: Sim):
    sim.hold("open_palm", 1000, move=(0.35, 0), start=(0.3, 0.75))  # slow
    sim.hold("fist", 300)
    sim.hold("open_palm", 250, move=(0.1, -0.35), start=(0.4, 0.85))  # mostly vertical
    assert _cmds(sim) == []


def test_sliding_does_not_cause_emergency_stop(sim: Sim):
    for i in range(6):  # 6 slides back and forth with the palm shown the whole ~2.4 s
        step = 0.35 if i % 2 == 0 else -0.35
        start = (0.3, 0.75) if i % 2 == 0 else (0.65, 0.75)
        sim.hold("open_palm", 400, move=(step, 0), start=start)
    assert not sim.controller.stopped
    sim.hold("open_palm", 1700, start=(0.3, 0.75))  # a still palm still stops
    assert sim.controller.stopped


def test_disabled(sim: Sim):
    sim.config["gestures"]["palm_slide"]["enabled"] = False
    sim.controller.configure(sim.config)
    sim.hold("open_palm", 200, start=(0.3, 0.75))
    sim.hold("open_palm", 250, move=(0.35, 0), start=(0.3, 0.75))
    assert _cmds(sim) == []
