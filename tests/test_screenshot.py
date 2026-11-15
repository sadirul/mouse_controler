"""Two-hand camera-frame gesture -> screenshot."""
from __future__ import annotations

from pathlib import Path

from app.hand_tracker import TrackedHand
from app.screenshot import is_frame_pose, take_screenshot
from app.simulation import synth_hand
from app.gesture_detector import extract_features
from tests.conftest import DT, Sim, default_config

L = {"middle": "folded", "ring": "folded", "pinky": "folded"}


def _l_hand(side: str, x: float, shape=L, thumb="extended") -> TrackedHand:
    return TrackedHand(synth_hand(shape, thumb=thumb, hand=side, center=(x, 0.7)), side, 0.95)


def _frame(sim: Sim, ms: float, right=None, left=None) -> None:
    right = right or _l_hand("Right", 0.68)
    left = left or _l_hand("Left", 0.32)
    for _ in range(max(1, int(ms / 1000 * 30))):
        sim.t += DT
        sim.results.append(sim.controller.process(right, sim.t, others=[left]))


def _sim_with_capture():
    sim = Sim(default_config())
    shots: list = []
    sim.controller.capture = lambda folder: shots.append(folder) or Path("shot.png")
    return sim, shots


def test_frame_pose_needs_two_l_hands():
    r = extract_features(_l_hand("Right", 0.68).landmarks, "Right")
    l = extract_features(_l_hand("Left", 0.32).landmarks, "Left")
    point = extract_features(synth_hand(L, thumb="folded", center=(0.32, 0.7)), "Left")
    assert is_frame_pose([r, l])
    assert not is_frame_pose([r])
    assert not is_frame_pose([r, point])


def test_holding_frame_takes_one_screenshot():
    sim, shots = _sim_with_capture()
    _frame(sim, 400)
    assert shots == []  # not held long enough yet
    _frame(sim, 3000)  # keeps holding: still exactly one shot
    assert len(shots) == 1
    assert any(k == "screenshot" for k, _ in sim.notices)
    assert sim.backend.calls == [] or all(c[0] != "click" for c in sim.backend.calls)


def test_second_screenshot_needs_release_and_cooldown():
    sim, shots = _sim_with_capture()
    _frame(sim, 1000)
    sim.hold(None, 300)
    _frame(sim, 1000)  # within the 2 s cooldown
    assert len(shots) == 1
    sim.hold(None, 1500)
    _frame(sim, 1000)
    assert len(shots) == 2


def test_frame_freezes_cursor():
    sim, _ = _sim_with_capture()
    _frame(sim, 1000)
    assert all(r.decision.cursor == "freeze" for r in sim.results[3:])


def test_disabled_and_stopped_do_not_capture():
    sim, shots = _sim_with_capture()
    sim.config["gestures"]["screenshot"]["enabled"] = False
    sim.controller.configure(sim.config)
    _frame(sim, 1500)
    sim.config["gestures"]["screenshot"]["enabled"] = True
    sim.controller.configure(sim.config)
    sim.controller.emergency_stop("Button")
    _frame(sim, 1500)
    assert shots == []


def test_take_screenshot_writes_png(tmp_path, monkeypatch):
    from PIL import Image, ImageGrab

    monkeypatch.setattr(ImageGrab, "grab", lambda **kw: Image.new("RGB", (8, 6), "red"))
    path = take_screenshot(tmp_path)
    assert path.exists() and path.suffix == ".png"
    assert take_screenshot(tmp_path) != path  # never overwrites
