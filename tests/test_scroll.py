"""Scroll controller and scroll-gesture state machine."""
from __future__ import annotations

import numpy as np

from app.gesture_classifier import Pose
from app.gesture_state import Ev, GestureStateMachine
from app.mouse_controller import MouseController
from app.scroll_controller import ScrollController
from tests.conftest import FakeMouseBackend, default_config, features_for


def test_scroll_controller_clamps_bursts():
    backend = FakeMouseBackend()
    sc = ScrollController(MouseController(backend), max_notches_per_event=5)
    assert sc.scroll(50.0) == (5.0, 0.0)
    assert sc.scroll(0, -20.0) == (0.0, -5.0)
    assert backend.of("wheel") == [("wheel", 5.0, 0.0), ("wheel", 0.0, -5.0)]


def test_scroll_controller_invert_and_zero():
    backend = FakeMouseBackend()
    sc = ScrollController(MouseController(backend), invert=True)
    sc.scroll(1.0)
    sc.scroll(0.0, 0.0)
    assert backend.of("wheel") == [("wheel", -1.0, 0.0)]


def _drive(machine, start, end, frames=20):
    t = 0.0
    events = []
    for i in range(frames + 10):
        frac = min(i / frames, 1.0)
        c = (start[0] + (end[0] - start[0]) * frac, start[1] + (end[1] - start[1]) * frac)
        f = features_for("two_finger", center=c)
        t += 1 / 30
        events += machine.update(Pose.TWO_FINGER, f, t).events
    return [e for e in events if e.kind == Ev.SCROLL]


def test_axis_lock_vertical_ignores_sideways_drift():
    m = GestureStateMachine(default_config()["gestures"])
    scrolls = _drive(m, (0.5, 0.75), (0.53, 0.55))
    assert scrolls
    assert all(e.data["dx"] == 0 for e in scrolls)
    assert sum(e.data["dy"] for e in scrolls) > 0


def test_horizontal_only_when_vertical_disabled():
    cfg = default_config()["gestures"]
    cfg["scroll_vertical"]["enabled"] = False
    m = GestureStateMachine(cfg)
    scrolls = _drive(m, (0.5, 0.75), (0.5, 0.55))
    assert not scrolls  # vertical motion ignored when only horizontal scrolling is enabled
    m.reset()
    scrolls = _drive(m, (0.5, 0.75), (0.35, 0.75))
    assert scrolls and sum(e.data["dx"] for e in scrolls) < 0


def test_scroll_amount_proportional_to_motion():
    m1 = GestureStateMachine(default_config()["gestures"])
    m2 = GestureStateMachine(default_config()["gestures"])
    small = sum(e.data["dy"] for e in _drive(m1, (0.5, 0.75), (0.5, 0.70)))
    large = sum(e.data["dy"] for e in _drive(m2, (0.5, 0.75), (0.5, 0.60)))
    assert large > small * 2


def test_disabled_scroll_never_scrolls():
    cfg = default_config()["gestures"]
    cfg["scroll"]["enabled"] = False
    m = GestureStateMachine(cfg)
    assert not _drive(m, (0.5, 0.75), (0.5, 0.5))


def test_scroll_jitter_dead_zone(rng):
    m = GestureStateMachine(default_config()["gestures"])
    t = 0.0
    events = []
    for _ in range(90):
        f = features_for("two_finger")
        f.norm = f.norm + np.concatenate([rng.normal(0, 0.0007, (21, 2)), np.zeros((21, 1))], axis=1)
        t += 1 / 30
        events += [e for e in m.update(Pose.TWO_FINGER, f, t).events if e.kind == Ev.SCROLL]
    assert not events
