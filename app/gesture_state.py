"""Gesture state machine.

Consumes debounced poses plus hand features once per frame and produces a :class:`Decision`:
how the cursor should behave this frame and which discrete events (click, scroll, window move...)
fired. It performs no OS calls, so every rule here is covered by unit tests.

Conflict handling: the machine is always in exactly one state. While a gesture owns the hand
(dragging, scrolling, moving a window, ...) other gestures are not evaluated until the owning
pose is released, and the emergency-stop palm is checked before everything else.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from app.gesture_classifier import Pose
from app.gesture_detector import HandFeatures


class State(str, Enum):
    IDLE = "idle"
    POINTING = "pointing"
    PINCH = "pinch"  # pinch down, deciding between click / long press / drag
    DRAGGING = "dragging"  # left button held
    WAIT_RELEASE = "wait_release"  # gesture consumed, waiting for the pose to end
    RIGHT_PINCH = "right_pinch"
    SCROLLING = "scrolling"
    WINDOW_MOVING = "window_moving"
    SWIPE = "swipe"
    HOLD_POSE = "hold_pose"
    STOPPED = "stopped"  # emergency stop


class Ev:
    CLICK_PENDING = "click_pending"  # a tap happened; single click deferred for double-click detection
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    LONG_PRESS = "long_press"  # long press in right-click mode
    MOUSE_DOWN = "mouse_down"
    MOUSE_UP = "mouse_up"
    SCROLL = "scroll"  # data: dx, dy in wheel notches (dy > 0 = up, dx > 0 = right)
    WINDOW_GRAB_START = "window_grab_start"
    WINDOW_MOVE = "window_move"  # data: dx, dy (normalised frame units since grab start)
    WINDOW_GRAB_END = "window_grab_end"
    WINDOW_COMMAND = "window_command"  # data: action, trigger, dialog
    CLOSE_ARMED = "close_armed"
    CLOSE_CANCELLED = "close_cancelled"
    EMERGENCY_STOP = "emergency_stop"
    RESUME = "resume"  # resume gesture held during an emergency stop


@dataclass
class Event:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Event({self.kind}, {self.data})"


@dataclass
class Decision:
    state: State
    pose: Pose
    cursor: str = "none"  # track | freeze | anchor | none
    point: np.ndarray | None = None  # index fingertip, normalised
    anchor: np.ndarray | None = None  # index knuckle, normalised (relative motion while pinching)
    precision: bool = False  # thumb approaching index: slow the cursor down
    events: list[Event] = field(default_factory=list)
    label: str = ""
    progress: float = 0.0
    progress_label: str = ""

    def kinds(self) -> list[str]:
        return [e.kind for e in self.events]


_NEUTRAL = {State.IDLE, State.POINTING}


class GestureStateMachine:
    def __init__(self, gestures_cfg: dict[str, Any] | None = None):
        self.cfg: dict[str, Any] = {}
        self.configure(gestures_cfg or {})
        self.reset()

    # ------------------------------------------------------------------ configuration
    def configure(self, cfg: dict[str, Any]) -> None:
        from app.settings_manager import DEFAULT_GESTURES

        merged = {k: dict(v) if isinstance(v, dict) else v for k, v in DEFAULT_GESTURES["gestures"].items()}
        for key, value in cfg.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        self.cfg = merged

    def _g(self, section: str, key: str, default: Any = None) -> Any:
        return self.cfg.get(section, {}).get(key, default)

    def _enabled(self, section: str) -> bool:
        return bool(self._g(section, "enabled", True))

    def reset(self) -> None:
        self.state = State.IDLE
        self._pinch_t0 = 0.0
        self._pinch_anchor0: np.ndarray | None = None
        self._pending_click_t: float | None = None
        self._pending_anchor: np.ndarray | None = None
        self._last_tap_t = -1e9
        self._last_fire: dict[str, float] = {}
        self._palm_since: float | None = None
        self._resume_since: float | None = None
        self._slide_samples: deque[tuple[float, np.ndarray]] = deque()
        self._slide_last: tuple[float, str] | None = None  # (time, direction) of the last slide
        self._scroll_origin: np.ndarray | None = None
        self._scroll_ref: np.ndarray | None = None
        self._scroll_smooth: np.ndarray | None = None
        self._scroll_axis: str | None = None
        self._scroll_t = 0.0
        self._win_origin: np.ndarray | None = None
        self._swipe_origin: np.ndarray | None = None
        self._swipe_t0 = 0.0
        self._hold_pose: Pose | None = None
        self._hold_t0 = 0.0
        self._wait_pose: Pose | None = None
        self._close_armed_until: float | None = None
        self._close_trigger: str | None = None
        self._button_down = False
        self._window_grabbed = False

    @property
    def button_down(self) -> bool:
        return self._button_down

    @property
    def stopped(self) -> bool:
        return self.state == State.STOPPED

    def resume(self) -> None:
        """Leave the emergency-stop state."""
        self.reset()

    def release_all(self) -> list[Event]:
        """End any gesture that holds an OS resource (mouse button, window grab)."""
        events: list[Event] = []
        if self._button_down:
            events.append(Event(Ev.MOUSE_UP))
            self._button_down = False
        if self._window_grabbed:
            events.append(Event(Ev.WINDOW_GRAB_END))
            self._window_grabbed = False
        return events

    # ------------------------------------------------------------------ helpers
    def _cooldown_ok(self, name: str, t: float, cooldown_ms: float | None = None) -> bool:
        if cooldown_ms is None:
            cooldown_ms = float(self._g(name, "cooldown_ms", 0))
        return (t - self._last_fire.get(name, -1e9)) * 1000.0 >= cooldown_ms

    def _fire(self, name: str, t: float) -> None:
        self._last_fire[name] = t

    def _window_pose(self) -> Pose:
        return Pose.THUMB_INDEX_MIDDLE if self._g("window_move", "pose") == "thumb_index_middle" else Pose.THREE_FINGER

    def _flush_pending_click(self, events: list[Event], t: float) -> None:
        if self._pending_click_t is not None:
            events.append(Event(Ev.CLICK))
            self._fire("click", t)
            self._pending_click_t = None
            self._pending_anchor = None

    # ------------------------------------------------------------------ main update
    def update(self, pose: Pose, features: HandFeatures | None, t: float) -> Decision:
        d = Decision(state=self.state, pose=pose)
        if features is not None:
            d.point = features.index_tip
            d.anchor = features.anchor

        if self.state == State.STOPPED:
            self._resume_check(pose, t, d)
            d.state = self.state
            return d

        events = d.events

        # 1. Deferred single click (double-click window expired)
        if self._pending_click_t is not None:
            interval = float(self._g("double_click", "interval_ms", 350)) / 1000.0
            if t - self._pending_click_t > interval:
                self._flush_pending_click(events, t)

        # 2. Close confirmation timeout
        if self._close_armed_until is not None and t > self._close_armed_until:
            self._close_armed_until = None
            self._close_trigger = None
            events.append(Event(Ev.CLOSE_CANCELLED))

        # 3. Emergency stop has priority over everything else
        if self._emergency_check(pose, features, t, d):
            return d

        # 4. Momentary tracking dropout: MediaPipe occasionally misses the hand for a frame while the
        #    debounced pose is still valid. Hold the current gesture instead of treating it as a
        #    release (which would drop a drag or turn a held pinch into a click). If the hand is
        #    really gone, the debounced pose becomes NONE after 250 ms and the gesture ends normally.
        if features is None and pose != Pose.NONE and self.state not in _NEUTRAL:
            d.cursor = "freeze"
            d.label = "Tracking lost - hold still"
            return d

        # 5. State handlers
        self._step(pose, features, t, d)
        d.state = self.state
        return d

    def _emergency_check(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> bool:
        if not self._enabled("emergency_stop"):
            self._palm_since = None
            return False
        palm = pose == Pose.OPEN_PALM
        if palm and f is not None and self._g("emergency_stop", "require_palm_facing", False):
            palm = f.palm_facing
        if not palm:
            self._palm_since = None
            return False
        if self._palm_since is None:
            self._palm_since = t
        hold = float(self._g("emergency_stop", "hold_ms", 1500)) / 1000.0
        progress = (t - self._palm_since) / hold
        if progress >= 1.0:
            # Do NOT send the pending click - stop means stop.
            self._pending_click_t = None
            events = self.release_all()
            if self._close_armed_until is not None:
                events.append(Event(Ev.CLOSE_CANCELLED))
            events.append(Event(Ev.EMERGENCY_STOP))
            d.events.extend(events)
            self.state = State.STOPPED
            d.state = self.state
            d.cursor = "none"
            d.label = "Emergency stop"
            d.progress = 1.0
            return True
        d.progress = progress
        d.progress_label = "Emergency stop"
        return False

    def _resume_pose(self) -> Pose:
        return Pose.HORNS if self._g("resume", "pose", "fist") == "horns" else Pose.FIST

    def _resume_check(self, pose: Pose, t: float, d: Decision) -> None:
        """While stopped: holding the resume pose long enough turns gesture control back on."""
        d.label = "Emergency stop"
        if not self._enabled("resume") or pose != self._resume_pose():
            self._resume_since = None
            return
        if self._resume_since is None:
            self._resume_since = t
        hold = float(self._g("resume", "hold_ms", 2000)) / 1000.0
        progress = (t - self._resume_since) / hold
        if progress < 1.0:
            d.progress = progress
            d.progress_label = "Resume"
            return
        self.reset()
        d.events.append(Event(Ev.RESUME))
        # Wait until the resume pose is released so it cannot trigger its normal action
        # (e.g. horns -> switch app) straight away.
        self._wait(pose, d, "Resumed - release to continue")
        d.progress = 1.0

    def _step(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> None:
        handler = {
            State.IDLE: self._neutral,
            State.POINTING: self._neutral,
            State.PINCH: self._pinch,
            State.DRAGGING: self._dragging,
            State.WAIT_RELEASE: self._wait_release,
            State.RIGHT_PINCH: self._right_pinch,
            State.SCROLLING: self._scrolling,
            State.WINDOW_MOVING: self._window_moving,
            State.SWIPE: self._swipe,
            State.HOLD_POSE: self._hold,
        }[self.state]
        handler(pose, f, t, d)

    def _to_idle(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> None:
        """Leave the current state and immediately evaluate the new pose."""
        self.state = State.IDLE
        self._neutral(pose, f, t, d)

    # ------------------------------------------------------------------ neutral
    def _neutral(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> None:
        events = d.events
        if f is None or pose == Pose.NONE:
            self.state = State.IDLE
            d.label = "No hand"
            return

        if pose == Pose.PINCH_INDEX and (self._enabled("click") or self._enabled("drag") or self._enabled("long_press")):
            cooldown = float(self._g("click", "cooldown_ms", 120))
            # The cooldown stops bounce after a finished click; it must not swallow the second
            # pinch of a quick double click (a single click is still pending then).
            if self._pending_click_t is None and (t - self._last_tap_t) * 1000.0 < cooldown:
                self._wait(pose, d, "Click cooldown")
                return
            self.state = State.PINCH
            self._pinch_t0 = t
            self._pinch_anchor0 = f.anchor.copy()
            d.cursor = "freeze"
            d.label = "Pinch"
            return

        if pose != Pose.POINT:
            # Any other gesture finalises a pending single click first.
            if pose not in (Pose.RELAXED, Pose.FIST, Pose.OPEN_PALM):
                self._flush_pending_click(events, t)

        if pose == Pose.PINCH_MIDDLE and self._enabled("right_click"):
            if self._cooldown_ok("right_click", t):
                events.append(Event(Ev.RIGHT_CLICK))
                self._fire("right_click", t)
                d.label = "Right click"
            else:
                d.label = "Right click (cooldown)"
            self.state = State.RIGHT_PINCH
            d.cursor = "freeze"
            return

        scroll_on = self._enabled("scroll") and (self._enabled("scroll_vertical") or self._enabled("scroll_horizontal"))
        if pose == Pose.TWO_FINGER and scroll_on:
            self.state = State.SCROLLING
            p = f.scroll_point.copy()
            self._scroll_origin = p.copy()
            self._scroll_ref = p.copy()
            self._scroll_smooth = p.copy()
            self._scroll_axis = None
            self._scroll_t = t
            d.label = "Scroll"
            return

        if pose == self._window_pose() and self._enabled("window_move"):
            self.state = State.WINDOW_MOVING
            self._win_origin = f.palm_center.copy()
            self._window_grabbed = True
            events.append(Event(Ev.WINDOW_GRAB_START))
            d.label = "Grab window"
            return

        if pose == Pose.FOUR_FINGER and self._enabled("window_swipe"):
            if self._cooldown_ok("window_swipe", t):
                self.state = State.SWIPE
                self._swipe_origin = f.palm_center.copy()
                self._swipe_t0 = t
                d.label = "Swipe"
            else:
                self._wait(pose, d, "Swipe cooldown")
            return

        if pose in (Pose.HORNS, Pose.PINCH_PINKY):
            section = "horns" if pose == Pose.HORNS else "thumb_pinky"
            if self._enabled(section):
                if self._cooldown_ok(section, t):
                    self.state = State.HOLD_POSE
                    self._hold_pose = pose
                    self._hold_t0 = t
                    d.label = "Hold"
                else:
                    self._wait(pose, d, "Cooldown")
                return

        if pose == Pose.OPEN_PALM and self._enabled("palm_slide"):
            self._slide_check(f, t, d)
        else:
            self._slide_samples.clear()

        if pose == Pose.POINT and self._enabled("move"):
            self.state = State.POINTING
            if self._pending_click_t is not None:
                # Keep the cursor still between the two pinches of a potential double click,
                # unless the hand clearly moves away.
                limit = float(self._g("drag", "move_threshold", 0.025)) * 1.5
                if self._pending_anchor is not None and np.linalg.norm(f.anchor - self._pending_anchor) > limit:
                    self._flush_pending_click(events, t)
                    d.cursor = "track"
                else:
                    d.cursor = "freeze"
            else:
                d.cursor = "track"
            # Precision zone: slow the cursor down while the thumb approaches the index finger.
            approach = float(self._g("click", "pinch_threshold", 0.28)) * 1.8
            if f.pinch["index"] < approach:
                d.precision = True
            d.label = "Move cursor"
            return

        self.state = State.IDLE
        d.label = {Pose.FIST: "Fist (paused cursor)", Pose.OPEN_PALM: "Open palm", Pose.RELAXED: "Relaxed"}.get(pose, "Idle")

    def _slide_check(self, f: HandFeatures, t: float, d: Decision) -> None:
        """Open hand slid quickly sideways -> flip to the next / previous app.

        The hand naturally swings back after a slide; that return stroke (opposite direction shortly
        after) is ignored so one slide never flips twice.
        """
        window = float(self._g("palm_slide", "window_ms", 400)) / 1000.0
        samples = self._slide_samples
        samples.append((t, f.palm_center.copy()))
        while samples and t - samples[0][0] > window:
            samples.popleft()
        delta = f.palm_center - samples[0][1]
        dx = delta[0] * f.aspect / f.hand_size
        dy = delta[1] / f.hand_size
        if abs(dx) < float(self._g("palm_slide", "distance", 1.2)) or abs(dx) < 2.0 * abs(dy):
            return
        direction = "right" if dx > 0 else "left"
        samples.clear()
        if self._slide_last is not None:
            last_t, last_dir = self._slide_last
            elapsed = (t - last_t) * 1000.0
            if elapsed < float(self._g("palm_slide", "cooldown_ms", 500)):
                return
            if last_dir != direction and elapsed < float(self._g("palm_slide", "return_ms", 900)):
                return  # the hand swinging back after the previous slide
        self._slide_last = (t, direction)
        self._palm_since = t  # sliding is not holding still: restart the emergency-stop timer
        d.progress = 0.0
        d.progress_label = ""
        self._flush_pending_click(d.events, t)
        self._trigger(f"palm_slide_{direction}", t, d)

    def _wait(self, pose: Pose, d: Decision, label: str) -> None:
        self.state = State.WAIT_RELEASE
        self._wait_pose = pose
        d.label = label

    def _wait_release(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> None:
        if pose == self._wait_pose:
            d.cursor = "freeze" if pose in (Pose.PINCH_INDEX, Pose.PINCH_MIDDLE) else "none"
            d.label = "Release to continue"
            return
        self._wait_pose = None
        self._to_idle(pose, f, t, d)

    # ------------------------------------------------------------------ pinch / click / drag
    def _pinch(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> None:
        events = d.events
        held_ms = (t - self._pinch_t0) * 1000.0
        if pose == Pose.PINCH_INDEX and f is not None:
            moved = float(np.linalg.norm(f.anchor - self._pinch_anchor0)) if self._pinch_anchor0 is not None else 0.0
            threshold = float(self._g("drag", "move_threshold", 0.025))
            if self._enabled("drag") and self._g("drag", "on_move", True) and moved > threshold:
                self._flush_pending_click(events, t)
                events.append(Event(Ev.MOUSE_DOWN, {"reason": "drag"}))
                self._button_down = True
                self.state = State.DRAGGING
                d.cursor = "anchor"
                d.label = "Drag"
                return
            duration = float(self._g("long_press", "duration_ms", 800))
            if self._enabled("long_press") and held_ms >= duration:
                self._flush_pending_click(events, t)
                if self._g("long_press", "mode", "hold") == "right_click":
                    events.append(Event(Ev.LONG_PRESS))
                    self._wait(pose, d, "Long press")
                    d.cursor = "freeze"
                else:
                    events.append(Event(Ev.MOUSE_DOWN, {"reason": "long_press"}))
                    self._button_down = True
                    self.state = State.DRAGGING
                    d.cursor = "anchor" if self._enabled("drag") else "freeze"
                    d.label = "Long press (holding)"
                return
            d.cursor = "freeze"
            d.label = "Pinch"
            if self._enabled("long_press"):
                d.progress = min(held_ms / duration, 1.0)
                d.progress_label = "Long press"
            return

        # Pinch released -> tap
        self._last_tap_t = t
        if self._enabled("click"):
            if self._pending_click_t is not None and self._enabled("double_click"):
                events.append(Event(Ev.DOUBLE_CLICK))
                self._fire("click", t)
                self._pending_click_t = None
                self._pending_anchor = None
                d.label = "Double click"
            elif self._enabled("double_click"):
                self._pending_click_t = t
                self._pending_anchor = self._pinch_anchor0.copy() if self._pinch_anchor0 is not None else None
                events.append(Event(Ev.CLICK_PENDING))
                d.label = "Click"
            else:
                events.append(Event(Ev.CLICK))
                self._fire("click", t)
                d.label = "Click"
        self.state = State.IDLE
        label = d.label
        self._neutral(pose, f, t, d)
        d.label = label or d.label

    def _dragging(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> None:
        if pose == Pose.PINCH_INDEX and f is not None:
            d.cursor = "anchor" if self._enabled("drag") else "freeze"
            d.label = "Dragging" if self._enabled("drag") else "Long press (holding)"
            return
        d.events.append(Event(Ev.MOUSE_UP))
        self._button_down = False
        self._last_tap_t = t
        label = "Drop"
        self._to_idle(pose, f, t, d)
        d.label = label

    def _right_pinch(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> None:
        if pose == Pose.PINCH_MIDDLE:
            d.cursor = "freeze"
            d.label = "Right click"
            return
        self._to_idle(pose, f, t, d)

    # ------------------------------------------------------------------ scrolling
    def _scrolling(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> None:
        if pose != Pose.TWO_FINGER or f is None:
            self._to_idle(pose, f, t, d)
            return
        d.cursor = "none"
        v_on = self._enabled("scroll_vertical")
        h_on = self._enabled("scroll_horizontal")
        raw = f.scroll_point
        self._scroll_smooth = 0.5 * raw + 0.5 * self._scroll_smooth
        p = self._scroll_smooth
        dt = max(t - self._scroll_t, 1e-3)
        self._scroll_t = t

        if self._scroll_axis is None:
            if v_on and not h_on:
                self._scroll_axis = "v"
            elif h_on and not v_on:
                self._scroll_axis = "h"
            else:
                total = p - self._scroll_origin
                lock = float(self._g("scroll", "axis_lock_threshold", 0.015))
                if max(abs(total[0]), abs(total[1])) > lock:
                    self._scroll_axis = "v" if abs(total[1]) >= abs(total[0]) else "h"
                    self._scroll_ref = self._scroll_origin.copy()
            if self._scroll_axis is None:
                d.label = "Scroll"
                return

        axis = 1 if self._scroll_axis == "v" else 0
        speed = float(self._g("scroll_vertical" if axis == 1 else "scroll_horizontal", "speed", 30.0))
        dead = float(self._g("scroll", "dead_zone", 0.003))
        amount = 0.0
        if self._g("scroll", "mode", "touchpad") == "joystick":
            offset = p[axis] - self._scroll_origin[axis]
            zone = max(dead * 10, 0.03)
            if abs(offset) > zone:
                amount = np.sign(offset) * (abs(offset) - zone) * speed * 4.0 * dt
        else:
            delta = p[axis] - self._scroll_ref[axis]
            if abs(delta) > dead:
                amount = delta * speed
                self._scroll_ref = p.copy()
        if amount:
            if axis == 1:
                dy = -amount  # fingers moving up (smaller y) scroll up (positive)
                d.events.append(Event(Ev.SCROLL, {"dx": 0.0, "dy": float(dy)}))
                d.label = "Scroll up" if dy > 0 else "Scroll down"
            else:
                d.events.append(Event(Ev.SCROLL, {"dx": float(amount), "dy": 0.0}))
                d.label = "Scroll right" if amount > 0 else "Scroll left"
        else:
            d.label = "Scroll (vertical)" if axis == 1 else "Scroll (horizontal)"

    # ------------------------------------------------------------------ window gestures
    def _window_moving(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> None:
        if pose == self._window_pose() and f is not None:
            delta = f.palm_center - self._win_origin
            d.events.append(Event(Ev.WINDOW_MOVE, {"dx": float(delta[0]), "dy": float(delta[1])}))
            d.label = "Moving window"
            return
        d.events.append(Event(Ev.WINDOW_GRAB_END))
        self._window_grabbed = False
        self._to_idle(pose, f, t, d)

    def _swipe(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> None:
        if pose != Pose.FOUR_FINGER or f is None:
            self._to_idle(pose, f, t, d)
            return
        d.label = "Swipe"
        window = float(self._g("window_swipe", "window_ms", 650)) / 1000.0
        if t - self._swipe_t0 > window:
            # sliding window: only quick motions count as swipes
            self._swipe_origin = f.palm_center.copy()
            self._swipe_t0 = t
            return
        delta = f.palm_center - self._swipe_origin
        # convert to hand sizes so the distance is independent of camera distance
        dist = np.array([delta[0] * f.aspect, delta[1]]) / f.hand_size
        needed = float(self._g("window_swipe", "distance", 0.9))
        if np.max(np.abs(dist)) < needed:
            return
        if abs(dist[0]) > abs(dist[1]):
            direction = "right" if dist[0] > 0 else "left"
        else:
            direction = "down" if dist[1] > 0 else "up"
        self._fire("window_swipe", t)
        self._trigger(f"four_swipe_{direction}", t, d)
        self._wait(pose, d, d.label)

    def _hold(self, pose: Pose, f: HandFeatures | None, t: float, d: Decision) -> None:
        if pose != self._hold_pose:
            self._hold_pose = None
            self._to_idle(pose, f, t, d)
            return
        section = "horns" if pose == Pose.HORNS else "thumb_pinky"
        hold = float(self._g(section, "hold_ms", 700))
        held = (t - self._hold_t0) * 1000.0
        trigger = "horns_hold" if pose == Pose.HORNS else "thumb_pinky_hold"
        action = self.cfg.get("mappings", {}).get(trigger, "none")
        d.progress = min(held / hold, 1.0)
        d.progress_label = action.replace("_", " ").title()
        d.label = d.progress_label
        if held >= hold:
            self._fire(section, t)
            self._trigger(trigger, t, d)
            self._wait(pose, d, d.label)

    def trigger(self, trigger: str, t: float, d: Decision) -> None:
        """Run a mapped trigger detected outside the state machine (two-hand gestures)."""
        self._flush_pending_click(d.events, t)
        self._trigger(trigger, t, d)

    def _trigger(self, trigger: str, t: float, d: Decision) -> None:
        action = self.cfg.get("mappings", {}).get(trigger, "none")
        if action == "none":
            d.label = "No action mapped"
            return
        if action == "close":
            confirm = self._g("close_confirm", "mode", "gesture")
            if confirm == "dialog":
                d.events.append(Event(Ev.WINDOW_COMMAND, {"action": "close", "trigger": trigger, "dialog": True}))
                d.label = "Close (confirm dialog)"
                return
            if self._close_armed_until is not None and self._close_trigger == trigger and t <= self._close_armed_until:
                self._close_armed_until = None
                self._close_trigger = None
                d.events.append(Event(Ev.WINDOW_COMMAND, {"action": "close", "trigger": trigger, "dialog": False}))
                d.label = "Close window"
            else:
                window = float(self._g("close_confirm", "window_ms", 4000)) / 1000.0
                self._close_armed_until = t + window
                self._close_trigger = trigger
                d.events.append(Event(Ev.CLOSE_ARMED, {"trigger": trigger, "seconds": window}))
                d.label = "Repeat to confirm close"
            return
        d.events.append(Event(Ev.WINDOW_COMMAND, {"action": action, "trigger": trigger, "dialog": False}))
        d.label = action.replace("_", " ").title()
