"""Finger detection, classification, and gesture state-machine behaviour."""
from __future__ import annotations

import numpy as np
import pytest

from app.gesture_classifier import Pose, PoseClassifier, PoseStabilizer
from app.gesture_detector import FingerState, MotionTracker, extract_features
from app.gesture_state import Ev, GestureStateMachine, State
from app.simulation import pose_landmarks
from tests.conftest import Sim, default_config, features_for

# --------------------------------------------------------------------------------------
# Finger detection
# --------------------------------------------------------------------------------------
EXPECTED_FINGERS = {
    "open_palm": dict(thumb="extended", index="extended", middle="extended", ring="extended", pinky="extended"),
    "fist": dict(thumb="folded", index="folded", middle="folded", ring="folded", pinky="folded"),
    "point": dict(index="extended", middle="folded", ring="folded", pinky="folded"),
    "two_finger": dict(index="extended", middle="extended", ring="folded", pinky="folded"),
    "three_finger": dict(index="extended", middle="extended", ring="extended", pinky="folded"),
    "four_finger": dict(thumb="folded", index="extended", middle="extended", ring="extended", pinky="extended"),
    "horns": dict(index="extended", middle="folded", ring="folded", pinky="extended"),
}


@pytest.mark.parametrize("hand", ["Right", "Left"])
@pytest.mark.parametrize("pose", list(EXPECTED_FINGERS))
def test_finger_states(pose, hand):
    f = features_for(pose, hand=hand)
    for finger, state in EXPECTED_FINGERS[pose].items():
        assert f.fingers[finger] == FingerState(state), f"{pose}/{hand}: {finger} is {f.fingers[finger]}"


def test_partial_finger_detected():
    f = features_for("open_palm", fingers={"index": "partial"})
    assert f.fingers["index"] == FingerState.PARTIAL


def test_all_21_landmarks_used():
    f = features_for("open_palm")
    assert f.points.shape == (21, 3)
    assert f.hand_size == pytest.approx(0.22, rel=0.05)


@pytest.mark.parametrize("distance", [0.12, 0.22, 0.35])
def test_features_scale_invariant(distance):
    f = features_for("pinch_index", size=distance)
    assert f.pinch["index"] < 0.15
    assert f.is_extended("index") or f.fingers["index"] == FingerState.PARTIAL


def test_touching_and_palm_center():
    f = features_for("pinch_middle")
    assert f.touching("middle", 0.2)
    assert not f.touching("index", 0.2)
    assert 0 < f.palm_center[0] < 1 and 0 < f.palm_center[1] < 1


def test_palm_facing_orientation():
    assert features_for("open_palm").palm_facing
    assert features_for("open_palm", hand="Left").palm_facing
    assert not features_for("open_palm", palm_facing=False).palm_facing


def test_motion_tracker_moving_and_stationary():
    mt = MotionTracker(alpha=1.0)
    t = 0.0
    for i in range(5):
        f = extract_features(pose_landmarks("point", center=(0.5, 0.75)))
        mt.update(f, t)
        t += 1 / 30
    assert f.stationary
    for i in range(5):
        f = extract_features(pose_landmarks("point", center=(0.5 + 0.02 * i, 0.75)))
        mt.update(f, t)
        t += 1 / 30
    assert f.moving
    assert f.finger_moving("index")


# --------------------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name,pose",
    [
        ("point", Pose.POINT),
        ("open_palm", Pose.OPEN_PALM),
        ("fist", Pose.FIST),
        ("pinch_index", Pose.PINCH_INDEX),
        ("pinch_middle", Pose.PINCH_MIDDLE),
        ("pinch_pinky", Pose.PINCH_PINKY),
        ("two_finger", Pose.TWO_FINGER),
        ("three_finger", Pose.THREE_FINGER),
        ("four_finger", Pose.FOUR_FINGER),
        ("horns", Pose.HORNS),
        ("v_sign", Pose.RELAXED),  # spread fingers are deliberately NOT a scroll gesture
    ],
)
@pytest.mark.parametrize("hand", ["Right", "Left"])
def test_classification(name, pose, hand):
    clf = PoseClassifier(default_config()["gestures"])
    assert clf.classify(features_for(name, hand=hand)) == pose


def test_fist_is_never_a_right_click():
    """In a fist the thumb rests near the folded middle finger - must not count as a pinch."""
    clf = PoseClassifier(default_config()["gestures"])
    f = features_for("fist")
    assert f.pinch["middle"] < 0.28  # geometrically close...
    assert clf.classify(f) == Pose.FIST  # ...but not a pinch


def test_window_pose_option_thumb_index_middle():
    cfg = default_config()["gestures"]
    cfg["window_move"]["pose"] = "thumb_index_middle"
    clf = PoseClassifier(cfg)
    assert clf.classify(features_for("thumb_index_middle")) == Pose.THUMB_INDEX_MIDDLE
    assert clf.classify(features_for("two_finger")) == Pose.TWO_FINGER


def test_pinch_hysteresis():
    clf = PoseClassifier(default_config()["gestures"])
    f = features_for("pinch_index")
    assert clf.classify(f) == Pose.PINCH_INDEX
    # Distance between on (0.28) and off (0.38) thresholds: stays pinched...
    f.pinch["index"] = 0.33
    assert clf.classify(f) == Pose.PINCH_INDEX
    # ...but a fresh classifier would not start a pinch at that distance.
    clf.reset()
    assert clf.classify(f) != Pose.PINCH_INDEX


def test_no_hand_is_none():
    assert PoseClassifier().classify(None) == Pose.NONE


def test_stabilizer_requires_min_duration():
    st = PoseStabilizer()
    assert st.update(Pose.TWO_FINGER, 0.0) == Pose.NONE
    assert st.update(Pose.TWO_FINGER, 0.05) == Pose.NONE
    assert st.update(Pose.TWO_FINGER, 0.13) == Pose.TWO_FINGER
    # a single-frame glitch does not change the stable pose
    assert st.update(Pose.FIST, 0.16) == Pose.TWO_FINGER
    assert st.update(Pose.TWO_FINGER, 0.19) == Pose.TWO_FINGER


# --------------------------------------------------------------------------------------
# Click / double click / pinch
# --------------------------------------------------------------------------------------
def test_single_click_once(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_index", 150)
    sim.hold("point", 600)  # wait past the double-click interval
    assert sim.backend.clicks("left") == 1
    assert sim.events().count(Ev.CLICK) == 1


def test_holding_pinch_does_not_repeat_clicks(sim: Sim):
    sim.config["gestures"]["long_press"]["enabled"] = False
    sim.controller.configure(sim.config)
    sim.hold("point", 200)
    sim.hold("pinch_index", 2000)
    sim.hold("point", 600)
    assert sim.backend.clicks("left") == 1


def test_double_click(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_index", 100)
    sim.hold("point", 130)
    sim.hold("pinch_index", 100)
    sim.hold("point", 600)
    events = sim.events()
    assert events.count(Ev.DOUBLE_CLICK) == 1
    assert events.count(Ev.CLICK) == 0, "a double click must not also produce single clicks"
    assert sim.backend.clicks("left") == 2  # the two button presses of the double click


def test_fast_double_click(sim: Sim):
    """Quick double pinch with only ~100 ms of release between pinches."""
    sim.hold("point", 300)
    sim.hold("pinch_index", 100)
    sim.hold("point", 100)
    sim.hold("pinch_index", 100)
    sim.hold("point", 600)
    assert sim.events().count(Ev.DOUBLE_CLICK) == 1
    assert Ev.CLICK not in sim.events()


def test_click_cooldown_blocks_bounce_after_double_click(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_index", 100)
    sim.hold("point", 100)
    sim.hold("pinch_index", 100)
    sim.hold("point", 100)
    sim.hold("pinch_index", 100)  # third pinch right after the double click: within cooldown
    sim.hold("point", 600)
    assert sim.events().count(Ev.DOUBLE_CLICK) == 1
    assert sim.backend.clicks("left") == 2


def test_two_slow_pinches_are_two_single_clicks(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_index", 100)
    sim.hold("point", 700)
    sim.hold("pinch_index", 100)
    sim.hold("point", 700)
    assert sim.events().count(Ev.CLICK) == 2
    assert Ev.DOUBLE_CLICK not in sim.events()


def test_click_happens_where_pinch_started(sim: Sim):
    sim.hold("point", 400)
    before = sim.backend.pos
    sim.hold("pinch_index", 120)
    sim.hold("point", 600)
    downs = [c for c in sim.backend.calls if c[0] == "down"]
    assert downs and downs[0][2] == before


def test_double_click_disabled_gives_immediate_click(sim: Sim):
    sim.config["gestures"]["double_click"]["enabled"] = False
    sim.controller.configure(sim.config)
    sim.hold("point", 300)
    sim.hold("pinch_index", 100)
    sim.hold("point", 150)
    assert sim.backend.clicks("left") == 1


def test_right_click_once(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_middle", 1500)
    sim.hold("point", 300)
    assert sim.backend.clicks("right") == 1
    assert sim.backend.clicks("left") == 0


def test_right_click_cooldown(sim: Sim):
    sim.hold("point", 200)
    sim.hold("pinch_middle", 150)
    sim.hold("point", 100)
    sim.hold("pinch_middle", 150)  # within the 400 ms cooldown
    sim.hold("point", 300)
    assert sim.backend.clicks("right") == 1


# --------------------------------------------------------------------------------------
# Long press and drag
# --------------------------------------------------------------------------------------
def test_long_press_hold_mode(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_index", 1200)
    assert "left" in sim.mouse.held_buttons
    sim.hold("point", 200)
    assert "left" not in sim.mouse.held_buttons
    assert Ev.CLICK not in sim.events()
    assert sim.events().count(Ev.MOUSE_DOWN) == 1


def test_long_press_right_click_mode(sim: Sim):
    sim.config["gestures"]["long_press"]["mode"] = "right_click"
    sim.controller.configure(sim.config)
    sim.hold("point", 300)
    sim.hold("pinch_index", 1200)
    sim.hold("point", 600)
    assert sim.backend.clicks("right") == 1
    assert sim.backend.clicks("left") == 0


def test_long_press_duration_configurable(sim: Sim):
    sim.config["gestures"]["long_press"]["duration_ms"] = 400
    sim.controller.configure(sim.config)
    sim.hold("point", 300)
    sim.hold("pinch_index", 600)
    assert "left" in sim.mouse.held_buttons


def test_drag_and_drop(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_index", 100, start=(0.5, 0.75))
    start_pos = sim.backend.pos
    sim.hold("pinch_index", 400, start=(0.5, 0.75), move=(0.15, 0.0))
    assert "left" in sim.mouse.held_buttons
    assert sim.controller.machine.state == State.DRAGGING
    assert sim.backend.pos[0] > start_pos[0] + 100, "cursor follows the hand while dragging"
    sim.hold("point", 200, start=(0.65, 0.75))
    assert "left" not in sim.mouse.held_buttons
    ev = sim.events()
    assert ev.count(Ev.MOUSE_DOWN) == 1 and ev.count(Ev.MOUSE_UP) == 1
    assert Ev.CLICK not in ev and Ev.CLICK_PENDING not in ev


def test_drag_disables_scroll_and_click(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_index", 100)
    sim.hold("pinch_index", 300, move=(0.1, 0.0))
    assert sim.controller.machine.state == State.DRAGGING
    # stray single frames of other poses are ignored by the stabiliser; drag continues
    sim.hold("two_finger", 30)
    sim.hold("pinch_index", 100, start=(0.6, 0.75))
    assert sim.controller.machine.state == State.DRAGGING
    assert not sim.backend.of("wheel")


def test_hand_lost_releases_drag(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_index", 100)
    sim.hold("pinch_index", 300, move=(0.1, 0.0))
    assert "left" in sim.mouse.held_buttons
    sim.hold(None, 500)
    assert "left" not in sim.mouse.held_buttons


def _dropout(sim: Sim, frames: int = 2):
    for _ in range(frames):
        sim.t += 1 / 30
        sim.controller.process(None, sim.t)


def test_single_frame_dropout_does_not_drop_drag(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_index", 100)
    sim.hold("pinch_index", 300, move=(0.1, 0.0))
    _dropout(sim, 2)
    assert "left" in sim.mouse.held_buttons
    sim.hold("pinch_index", 200, start=(0.6, 0.75))
    assert "left" in sim.mouse.held_buttons
    assert sim.events().count(Ev.MOUSE_UP) == 0


def test_dropout_during_pinch_is_not_a_click(sim: Sim):
    sim.config["gestures"]["long_press"]["enabled"] = False
    sim.controller.configure(sim.config)
    sim.hold("point", 300)
    sim.hold("pinch_index", 200)
    _dropout(sim, 2)
    assert sim.backend.clicks("left") == 0 and Ev.CLICK_PENDING not in sim.events()
    sim.hold("pinch_index", 200)
    sim.hold("point", 600)
    assert sim.backend.clicks("left") == 1


def test_dropout_does_not_reset_emergency_timer(sim: Sim):
    sim.hold("open_palm", 900)
    _dropout(sim, 2)
    assert not sim.controller.stopped
    sim.hold("open_palm", 800)  # reaches 1.5 s only if the timer kept running through the dropout
    assert sim.controller.stopped


def test_drag_disabled_holds_still(sim: Sim):
    sim.config["gestures"]["drag"]["enabled"] = False
    sim.controller.configure(sim.config)
    sim.hold("point", 300)
    sim.hold("pinch_index", 100)
    sim.hold("pinch_index", 300, move=(0.1, 0.0))
    assert "left" not in sim.mouse.held_buttons


# --------------------------------------------------------------------------------------
# Scrolling
# --------------------------------------------------------------------------------------
def _wheel_totals(sim: Sim) -> tuple[float, float]:
    v = sum(c[1] for c in sim.backend.of("wheel"))
    h = sum(c[2] for c in sim.backend.of("wheel"))
    return v, h


@pytest.mark.parametrize(
    "move,expect",
    [((0.0, -0.15), "up"), ((0.0, 0.15), "down"), ((0.15, 0.0), "right"), ((-0.15, 0.0), "left")],
)
def test_scroll_direction(sim: Sim, move, expect):
    sim.hold("two_finger", 200)
    sim.hold("two_finger", 500, move=move)
    v, h = _wheel_totals(sim)
    if expect == "up":
        assert v > 1 and h == 0
    elif expect == "down":
        assert v < -1 and h == 0
    elif expect == "right":
        assert h > 1 and v == 0
    else:
        assert h < -1 and v == 0


def test_scroll_speed_configurable():
    slow, fast = Sim(), Sim()
    fast.config["gestures"]["scroll_vertical"]["speed"] = 60.0
    fast.controller.configure(fast.config)
    for s in (slow, fast):
        s.hold("two_finger", 200)
        s.hold("two_finger", 500, move=(0, -0.1))
    assert _wheel_totals(fast)[0] > _wheel_totals(slow)[0] * 1.5


def test_still_hand_does_not_scroll(sim: Sim):
    sim.hold("two_finger", 1000)
    assert not sim.backend.of("wheel")


def test_pointing_never_scrolls(sim: Sim):
    sim.hold("point", 200)
    sim.hold("point", 500, move=(0, -0.2))
    assert not sim.backend.of("wheel")
    assert sim.backend.of("move")


def test_scroll_joystick_mode(sim: Sim):
    sim.config["gestures"]["scroll"]["mode"] = "joystick"
    sim.controller.configure(sim.config)
    sim.hold("two_finger", 200)
    sim.hold("two_finger", 200, move=(0, -0.12))
    sim.hold("two_finger", 600, start=(0.5, 0.63))  # hold the offset: keeps scrolling
    assert _wheel_totals(sim)[0] > 1


# --------------------------------------------------------------------------------------
# Window gestures
# --------------------------------------------------------------------------------------
def test_window_grab_and_move(sim: Sim):
    sim.hold("three_finger", 400)
    sim.hold("three_finger", 300, move=(0.1, 0.05))
    sim.hold("point", 200, start=(0.6, 0.8))
    kinds = [c[0] for c in sim.windows.calls]
    assert kinds[0] == "begin" and kinds[-1] == "end"
    moves = [c for c in sim.windows.calls if c[0] == "move_by"]
    assert moves[-1][1] > 100 and moves[-1][2] > 30


def test_window_titlebar_mode(sim: Sim):
    sim.config["gestures"]["window_move"]["mode"] = "titlebar"
    sim.controller.configure(sim.config)
    sim.hold("three_finger", 400)
    assert "left" in sim.mouse.held_buttons
    sim.hold("three_finger", 300, move=(0.1, 0.0))
    sim.hold("fist", 300)
    assert "left" not in sim.mouse.held_buttons


@pytest.mark.parametrize(
    "move,action",
    [((0, -0.3), "maximize"), ((0, 0.25), "restore_or_minimize"), ((-0.3, 0), "snap_left"), ((0.3, 0), "snap_right")],
)
def test_four_finger_swipes(sim: Sim, move, action):
    sim.hold("four_finger", 150)
    sim.hold("four_finger", 300, move=move)
    sim.hold("fist", 200)
    assert ("command", action) in sim.windows.calls
    assert len([c for c in sim.windows.calls if c[0] == "command"]) == 1


def test_slow_four_finger_motion_is_not_a_swipe(sim: Sim):
    sim.hold("four_finger", 150)
    sim.hold("four_finger", 3000, move=(0.0, -0.3))
    assert not [c for c in sim.windows.calls if c[0] == "command"]


def test_horns_switch_app(sim: Sim):
    sim.hold("horns", 1000)
    sim.hold("fist", 200)
    assert ("command", "switch_app") in sim.windows.calls


def test_close_requires_confirmation(sim: Sim):
    sim.hold("pinch_pinky", 1000)
    sim.hold("fist", 300)
    assert ("command", "close") not in sim.windows.calls
    assert any(k == "close_armed" for k, _ in sim.notices)
    sim.hold("pinch_pinky", 1000)
    sim.hold("fist", 300)
    assert ("command", "close") in sim.windows.calls


def test_close_confirmation_expires(sim: Sim):
    sim.hold("pinch_pinky", 1000)
    sim.hold("fist", 4500)
    sim.hold("pinch_pinky", 1000)
    assert ("command", "close") not in sim.windows.calls
    assert any(k == "close_cancelled" for k, _ in sim.notices)


def test_close_dialog_mode(sim: Sim):
    sim.config["gestures"]["close_confirm"]["mode"] = "dialog"
    sim.controller.configure(sim.config)
    sim.hold("pinch_pinky", 1000)
    assert ("command", "close") not in sim.windows.calls
    assert any(k == "confirm_close" for k, _ in sim.notices)


def test_mapping_change(sim: Sim):
    sim.config["gestures"]["mappings"]["horns_hold"] = "minimize"
    sim.controller.configure(sim.config)
    sim.hold("horns", 1000)
    assert ("command", "minimize") in sim.windows.calls


# --------------------------------------------------------------------------------------
# Priority, emergency stop, pause, disabled gestures
# --------------------------------------------------------------------------------------
def test_emergency_stop_by_open_palm(sim: Sim):
    sim.hold("point", 300)
    sim.hold("open_palm", 1700)
    assert sim.controller.stopped
    assert any(k == "emergency_stop" for k, _ in sim.notices)
    n = len(sim.backend.calls)
    sim.hold("point", 300, move=(0.2, 0))
    sim.hold("pinch_index", 200)
    sim.hold("point", 600)
    assert len(sim.backend.calls) == n, "no OS actions after an emergency stop"
    sim.controller.resume_from_stop()
    sim.hold("point", 300, move=(0.1, 0))
    assert len(sim.backend.calls) > n


def test_short_open_palm_does_not_stop(sim: Sim):
    sim.hold("open_palm", 800)
    sim.hold("point", 300)
    assert not sim.controller.stopped


def test_emergency_stop_has_priority_over_drag(sim: Sim):
    m = GestureStateMachine(default_config()["gestures"])
    pinch = features_for("pinch_index")
    palm = features_for("open_palm")
    t = 0.0
    m.update(Pose.PINCH_INDEX, pinch, t)
    t += 1.0
    m.update(Pose.PINCH_INDEX, pinch, t)  # long press -> button down
    assert m.button_down
    events = []
    for _ in range(60):
        t += 1 / 30
        events += m.update(Pose.OPEN_PALM, palm, t).kinds()
    assert Ev.MOUSE_UP in events and Ev.EMERGENCY_STOP in events
    assert events.index(Ev.MOUSE_UP) < events.index(Ev.EMERGENCY_STOP)
    assert m.state == State.STOPPED and not m.button_down


def test_emergency_hold_configurable(sim: Sim):
    sim.config["gestures"]["emergency_stop"]["hold_ms"] = 600
    sim.controller.configure(sim.config)
    sim.hold("open_palm", 900)
    assert sim.controller.stopped


def test_resume_gesture_after_emergency_stop(sim: Sim):
    sim.hold("open_palm", 1700)
    assert sim.controller.stopped
    sim.hold("fist", 1000)  # too short
    assert sim.controller.stopped
    sim.hold("fist", 2300)
    assert not sim.controller.stopped
    assert any(k == "resumed" for k, _ in sim.notices)
    n = len(sim.backend.calls)
    sim.hold("point", 300, move=(0.1, 0))
    assert len(sim.backend.calls) > n, "cursor moves again after resuming"


def test_resume_gesture_can_be_disabled(sim: Sim):
    sim.config["gestures"]["resume"]["enabled"] = False
    sim.controller.configure(sim.config)
    sim.hold("open_palm", 1700)
    sim.hold("fist", 3000)
    assert sim.controller.stopped


def test_resume_pose_must_be_released_before_its_action():
    cfg = default_config()["gestures"]
    cfg["resume"]["pose"] = "horns"
    cfg["resume"]["hold_ms"] = 500
    m = GestureStateMachine(cfg)
    m.state = State.STOPPED
    horns = features_for("horns")
    t, events = 0.0, []
    for _ in range(90):  # 3 s of horns: resumes, but must not also trigger switch_app
        t += 1 / 30
        events += m.update(Pose.HORNS, horns, t).kinds()
    assert Ev.RESUME in events and Ev.WINDOW_COMMAND not in events
    assert m.state == State.WAIT_RELEASE


def test_manual_emergency_stop_releases_buttons(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_index", 1200)
    assert "left" in sim.mouse.held_buttons
    sim.controller.emergency_stop("Button")
    assert "left" not in sim.mouse.held_buttons
    assert sim.controller.stopped


def test_pause_blocks_actions_and_releases(sim: Sim):
    sim.hold("point", 300)
    sim.hold("pinch_index", 1200)
    sim.controller.pause()
    assert "left" not in sim.mouse.held_buttons
    n = len(sim.backend.calls)
    sim.hold("point", 500, move=(0.2, 0))
    assert len(sim.backend.calls) == n
    sim.controller.resume()
    sim.hold("point", 300, move=(0.1, 0))
    assert len(sim.backend.calls) > n


@pytest.mark.parametrize(
    "gesture,pose",
    [("click", "pinch_index"), ("right_click", "pinch_middle")],
)
def test_disabled_gestures_do_nothing(gesture, pose):
    s = Sim()
    s.config["gestures"][gesture]["enabled"] = False
    if gesture == "click":
        for g in ("drag", "long_press"):
            s.config["gestures"][g]["enabled"] = False
    s.controller.configure(s.config)
    s.hold("point", 300)
    s.hold(pose, 200)
    s.hold("point", 600)
    assert not [c for c in s.backend.calls if c[0] in ("down", "up")]


def test_fist_freezes_cursor(sim: Sim):
    sim.hold("point", 300)
    sim.hold("fist", 200)
    n = len(sim.backend.of("move"))
    sim.hold("fist", 400, move=(0.2, 0.0))
    assert len(sim.backend.of("move")) == n


def test_left_hand_preference_end_to_end():
    s = Sim()
    s.hold("point", 300, hand="Left")
    s.hold("pinch_index", 120, hand="Left")
    s.hold("point", 600, hand="Left")
    assert s.backend.clicks("left") == 1


def test_noise_robustness(rng):
    """Landmark jitter of ~0.3% of the frame must not create clicks while pointing."""
    s = Sim()
    from app.hand_tracker import TrackedHand

    for _ in range(150):
        lm = pose_landmarks("point") + rng.normal(0, 0.003, (21, 3))
        s.t += 1 / 30
        s.controller.process(TrackedHand(lm, "Right", 0.95), s.t)
    assert not [c for c in s.backend.calls if c[0] in ("down", "up")]
