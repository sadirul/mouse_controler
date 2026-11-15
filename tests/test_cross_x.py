"""Two index fingers crossed like an X -> lock Windows (remappable)."""
from __future__ import annotations

from app.gesture_detector import extract_features
from app.hand_tracker import TrackedHand
from app.screenshot import is_cross_pose
from app.simulation import POSES, synth_hand
from tests.conftest import DT, Sim

POINT = POSES["point"]


def _hand(side: str, x: float, tilt: float, **kw) -> TrackedHand:
    return TrackedHand(synth_hand(**{**POINT, **kw}, hand=side, center=(x, 0.8), tilt=tilt), side, 0.95)


def _feat(h: TrackedHand):
    return extract_features(h.landmarks, h.handedness)


def _show(sim: Sim, ms: float, right: TrackedHand, left: TrackedHand) -> None:
    for _ in range(max(1, int(ms / 1000 * 30))):
        sim.t += DT
        sim.results.append(sim.controller.process(right, sim.t, others=[left]))


def _x(sim: Sim, ms: float) -> None:
    _show(sim, ms, _hand("Right", 0.70, -35), _hand("Left", 0.30, 35))


def _locks(sim: Sim) -> int:
    return sim.windows.calls.count(("command", "lock_screen"))


def test_detects_only_a_real_x():
    assert is_cross_pose([_feat(_hand("Right", 0.70, -35)), _feat(_hand("Left", 0.30, 35))])
    assert not is_cross_pose([_feat(_hand("Right", 0.6, 0)), _feat(_hand("Left", 0.4, 0))])  # side by side
    assert not is_cross_pose([_feat(_hand("Right", 0.62, -10)), _feat(_hand("Left", 0.38, 10))])  # barely tilted
    assert not is_cross_pose([_feat(_hand("Right", 0.70, -35))])  # one hand


def test_holding_x_locks_once(sim: Sim):
    _x(sim, 300)
    assert _locks(sim) == 0  # not held long enough
    _x(sim, 2000)
    assert _locks(sim) == 1
    assert all(r.decision.cursor == "freeze" for r in sim.results[-30:])


def test_x_needs_release_and_cooldown(sim: Sim):
    _x(sim, 800)
    sim.hold(None, 300)
    _x(sim, 800)  # within the 3 s cooldown
    assert _locks(sim) == 1
    sim.hold(None, 3000)
    _x(sim, 800)
    assert _locks(sim) == 2


def test_x_with_thumbs_out_is_not_a_screenshot(sim: Sim):
    shots = []
    sim.controller.capture = lambda folder: shots.append(folder) or "x.png"
    _show(sim, 1500, _hand("Right", 0.70, -35, thumb="extended"), _hand("Left", 0.30, 35, thumb="extended"))
    assert _locks(sim) == 1 and shots == []


def test_x_disabled_and_remapped(sim: Sim):
    sim.config["gestures"]["cross_x"]["enabled"] = False
    sim.controller.configure(sim.config)
    _x(sim, 1500)
    assert _locks(sim) == 0
    sim.config["gestures"]["cross_x"]["enabled"] = True
    sim.config["gestures"]["mappings"]["cross_x"] = "minimize"
    sim.controller.configure(sim.config)
    sim.hold(None, 300)
    _x(sim, 1500)
    assert ("command", "minimize") in sim.windows.calls and _locks(sim) == 0


def test_no_x_during_emergency_stop(sim: Sim):
    sim.controller.emergency_stop("Button")
    _x(sim, 1500)
    assert _locks(sim) == 0
