"""Glue between perception and action.

Per frame: hand landmarks -> :mod:`gesture_detector` features -> :mod:`gesture_classifier` pose
-> :mod:`gesture_state` decision -> cursor / mouse / scroll / window controllers.

Every OS action is wrapped so a failure (e.g. an elevated window refusing input) is logged to the
activity log instead of crashing the tracking loop, and held mouse buttons are always released
when control stops for any reason.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from app.cursor_controller import CursorController, Rect
from app.gesture_classifier import POSE_LABELS, Pose, PoseClassifier, PoseStabilizer
from app.gesture_detector import HandFeatures, MotionTracker, extract_features
from app.gesture_state import Decision, Ev, Event, GestureStateMachine, State
from app.hand_tracker import TrackedHand
from app.logger import ActivityLog
from app.mouse_controller import MouseController
from app import recycle_bin
from app.screenshot import CrossGesture, FrameGesture, take_screenshot
from app.scroll_controller import ScrollController
from app.window_controller import WindowController, WindowError

log = logging.getLogger(__name__)

EVENT_GESTURE = {
    Ev.CLICK: "Thumb + index pinch",
    Ev.DOUBLE_CLICK: "Two quick pinches",
    Ev.RIGHT_CLICK: "Thumb + middle pinch",
    Ev.LONG_PRESS: "Hold pinch",
    Ev.MOUSE_DOWN: "Hold / move pinch",
    Ev.MOUSE_UP: "Release pinch",
    Ev.SCROLL: "Two fingers",
    Ev.WINDOW_GRAB_START: "Three fingers",
    Ev.WINDOW_GRAB_END: "Three fingers released",
    Ev.WINDOW_COMMAND: "Window gesture",
    Ev.CLOSE_ARMED: "Thumb + pinky hold",
    Ev.CLOSE_CANCELLED: "Close confirmation",
    Ev.EMERGENCY_STOP: "Open palm (hold)",
    Ev.RESUME: "Resume gesture (hold)",
}

TRIGGER_GESTURE = {
    "four_swipe_up": "Four-finger swipe up",
    "four_swipe_down": "Four-finger swipe down",
    "four_swipe_left": "Four-finger swipe left",
    "four_swipe_right": "Four-finger swipe right",
    "horns_hold": "Horns hold",
    "thumb_pinky_hold": "Thumb + pinky hold",
    "palm_slide_left": "Open hand slide left",
    "palm_slide_right": "Open hand slide right",
    "cross_x": "Crossed index fingers (X)",
}


@dataclass
class FrameResult:
    features: HandFeatures | None
    raw_pose: Pose
    pose: Pose
    decision: Decision
    cursor: tuple[int, int] | None


class GestureController:
    def __init__(
        self,
        settings: dict[str, Any],
        mouse: MouseController,
        windows: WindowController,
        activity: ActivityLog,
        screen: Rect,
        notify: Callable[[str, dict], None] | None = None,
    ):
        self.mouse = mouse
        self.scroller = ScrollController(mouse)
        self.windows = windows
        self.activity = activity
        self.notify = notify or (lambda kind, data: None)
        self.classifier = PoseClassifier()
        self.stabilizer = PoseStabilizer()
        self.machine = GestureStateMachine()
        self.motion = MotionTracker()
        self.cursor = CursorController(screen)
        self.frame = FrameGesture()
        self.cross = CrossGesture()
        self.capture: Callable[[str | None], Any] = take_screenshot  # replaced in tests
        self.bin_query: Callable[[], tuple[int, int]] = recycle_bin.query  # replaced in tests
        self.paused = False
        self._pending_click_pos: tuple[int, int] | None = None
        self._titlebar_start: tuple[int, int] | None = None
        self._last_cursor_mode = "none"
        self._last_error_t = 0.0
        self.configure(settings)

    # ------------------------------------------------------------------ configuration
    def configure(self, settings: dict[str, Any]) -> None:
        self.settings = settings
        gestures = settings.get("gestures", {})
        self.classifier.configure(gestures)
        self.stabilizer.configure(gestures)
        self.machine.configure(gestures)
        self.frame.configure(self.machine.cfg.get("screenshot", {}))
        self.cross.configure(self.machine.cfg.get("cross_x", {}))
        self.cursor.configure(settings.get("cursor", {}))
        self.window_cfg = self.machine.cfg.get("window_move", {})

    def set_screen(self, screen: Rect) -> None:
        self.cursor.set_screen(screen)

    # ------------------------------------------------------------------ control state
    @property
    def stopped(self) -> bool:
        return self.machine.stopped

    def pause(self) -> None:
        if self.paused:
            return
        self._release_everything()
        self.paused = True
        self.activity.add("Control", "Paused")

    def resume(self) -> None:
        if not self.paused:
            return
        self.paused = False
        self._reset_tracking_state()
        self.activity.add("Control", "Resumed")

    def emergency_stop(self, source: str = "Button") -> None:
        if self.machine.stopped:
            return
        self._release_everything()
        self.machine.state = State.STOPPED
        self.activity.add(source, "Emergency stop - all gesture actions disabled")
        self.notify("emergency_stop", {"source": source})

    def resume_from_stop(self) -> None:
        if not self.machine.stopped:
            return
        self.machine.resume()
        self._reset_tracking_state()
        self.activity.add("Control", "Resumed after emergency stop")
        self.notify("resumed", {})

    def switch_hand(self) -> None:
        """Control moved to the other hand: end any gesture the previous hand was holding."""
        self._release_everything()
        self.motion.reset()
        self.stabilizer.reset()
        self.classifier.reset()
        self.cursor.reset()

    def _reset_tracking_state(self) -> None:
        self.machine.reset()
        self.stabilizer.reset()
        self.classifier.reset()
        self.cursor.reset()
        self._pending_click_pos = None

    def _release_everything(self) -> None:
        for event in self.machine.release_all():
            self._execute(event)
        try:
            self.mouse.release_all()
        except Exception:
            log.exception("release_all failed")
        if self.windows.grabbing:
            self.windows.end_move()
        if not self.machine.stopped:
            self.machine.reset()
        self._pending_click_pos = None

    def shutdown(self) -> None:
        self._release_everything()

    # ------------------------------------------------------------------ per-frame processing
    def process(
        self,
        hand: TrackedHand | None,
        t: float,
        aspect: float = 4 / 3,
        mirrored: bool = True,
        others: list[TrackedHand] | None = None,
    ) -> FrameResult:
        """Process one frame. ``others`` are the remaining visible hands (two-hand gestures)."""
        features = None
        if hand is not None:
            features = extract_features(hand.landmarks, hand.handedness, hand.score, aspect, mirrored)
        self.motion.update(features, t)
        raw = self.classifier.classify(features)
        pose = self.stabilizer.update(raw, t)

        if self.paused:
            decision = Decision(state=self.machine.state, pose=pose, label="Paused")
            return FrameResult(features, raw, pose, decision, self.cursor.position)

        frame_result = self._frame_gesture(features, others or [], t, aspect, mirrored, pose)
        if frame_result is not None:
            return frame_result

        decision = self.machine.update(pose, features, t)
        if decision.cursor == "track" and raw in (Pose.PINCH_INDEX, Pose.PINCH_MIDDLE):
            # A pinch is forming but not yet confirmed by the debouncer: hold the cursor still so
            # the curling fingertip does not drag it away from the click target.
            decision.cursor = "freeze"
        cursor_pos = self._apply_cursor(decision, t)
        for event in decision.events:
            self._execute(event)
        return FrameResult(features, raw, pose, decision, cursor_pos)

    def _frame_gesture(self, features, others, t, aspect, mirrored, pose) -> FrameResult | None:
        """Two-hand camera-frame gesture. Returns a result while it owns the hands, else None."""
        # Only start from a neutral state so a drag / window move is never interrupted.
        if self.machine.stopped or self.machine.state not in (State.IDLE, State.POINTING):
            self.frame.update([], t)
            self.cross.update([], t)
            return None
        hands = [features] if features is not None else []
        hands += [extract_features(h.landmarks, h.handedness, h.score, aspect, mirrored) for h in others]

        cross = self.cross.update(hands, t)
        if cross.active:
            self.frame.update([], t)
            action = self.machine.cfg.get("mappings", {}).get("cross_x", "none")
            title = action.replace("_", " ").title()
            decision = Decision(state=self.machine.state, pose=pose, cursor="freeze", label=f"X: {title}",
                                progress=cross.progress, progress_label=title)
            self.cursor.freeze()
            if cross.fired:
                self.machine.trigger("cross_x", t, decision)
                for event in decision.events:
                    self._execute(event)
            elif cross.progress >= 1.0:
                decision.label = "Done - uncross your fingers"
            return FrameResult(features, pose, pose, decision, self.cursor.position)

        status = self.frame.update(hands, t)
        if not status.active:
            return None
        decision = Decision(state=self.machine.state, pose=pose, cursor="freeze", label="Screenshot",
                            progress=status.progress, progress_label="Screenshot")
        self.cursor.freeze()
        if status.fired:
            folder = self.machine.cfg.get("screenshot", {}).get("folder") or None
            try:
                path = self.capture(folder)
                self.activity.add("Two-hand frame", f"Screenshot saved to {path}")
                self.notify("screenshot", {"path": str(path)})
                decision.label = "Screenshot saved"
            except Exception as exc:
                log.exception("Screenshot failed")
                self.activity.add("Two-hand frame", "Screenshot", success=False, error=str(exc))
                decision.label = "Screenshot failed"
        elif status.progress >= 1.0:
            decision.label = "Screenshot taken - lower your hands"
        return FrameResult(features, pose, pose, decision, self.cursor.position)

    def _apply_cursor(self, d: Decision, t: float) -> tuple[int, int] | None:
        mode = d.cursor
        new = None
        try:
            if mode == "track" and d.point is not None:
                if self._last_cursor_mode != "track" and self.cursor.mode == "relative":
                    self.cursor.sync(*self.mouse.position())
                new = self.cursor.track(d.point, t, precision=d.precision)
            elif mode == "anchor" and d.anchor is not None:
                if self.cursor.position is None:
                    self.cursor.sync(*self.mouse.position())
                new = self.cursor.anchor(d.anchor, t)
            else:
                self.cursor.freeze()
            if new is not None:
                self.mouse.move(*new)
        except Exception as exc:
            self._error("Cursor", "Move cursor", exc)
        self._last_cursor_mode = mode
        return self.cursor.position

    # ------------------------------------------------------------------ actions
    def _error(self, gesture: str, action: str, exc: Exception) -> None:
        now = time.monotonic()
        if now - self._last_error_t > 1.0:  # avoid flooding the log at 30 FPS
            self.activity.add(gesture, action, success=False, error=str(exc))
            self._last_error_t = now
        log.debug("%s failed", action, exc_info=True)

    def _execute(self, event: Event) -> None:
        kind = event.kind
        gesture = EVENT_GESTURE.get(kind, kind)
        try:
            if kind == Ev.CLICK_PENDING:
                self._pending_click_pos = self.mouse.position()
            elif kind == Ev.CLICK:
                self._move_to_pending()
                self.mouse.click("left")
                self.activity.add(gesture, "Left click")
            elif kind == Ev.DOUBLE_CLICK:
                self._move_to_pending()
                self.mouse.double_click()
                self.activity.add(gesture, "Double click")
            elif kind == Ev.RIGHT_CLICK:
                self.mouse.click("right")
                self.activity.add(gesture, "Right click")
            elif kind == Ev.LONG_PRESS:
                self.mouse.click("right")
                self.activity.add(gesture, "Long press -> right click")
            elif kind == Ev.MOUSE_DOWN:
                self.mouse.down("left")
                reason = event.data.get("reason")
                self.activity.add(gesture, "Long press (button held)" if reason == "long_press" else "Drag started")
            elif kind == Ev.MOUSE_UP:
                if "left" in self.mouse.held_buttons:
                    self.mouse.up("left")
                    self.activity.add(gesture, "Drop / button released")
            elif kind == Ev.SCROLL:
                self.scroller.scroll(event.data.get("dy", 0.0), event.data.get("dx", 0.0))
            elif kind == Ev.WINDOW_GRAB_START:
                self._window_grab_start(gesture)
            elif kind == Ev.WINDOW_MOVE:
                self._window_move(event.data["dx"], event.data["dy"])
            elif kind == Ev.WINDOW_GRAB_END:
                self._window_grab_end(gesture)
            elif kind == Ev.WINDOW_COMMAND:
                self._window_command(event)
            elif kind == Ev.CLOSE_ARMED:
                self.activity.add(gesture, "Close armed - repeat the gesture to confirm")
                self.notify("close_armed", event.data)
            elif kind == Ev.CLOSE_CANCELLED:
                self.activity.add(gesture, "Close cancelled (not confirmed)")
                self.notify("close_cancelled", {})
            elif kind == Ev.EMERGENCY_STOP:
                try:
                    self.mouse.release_all()
                finally:
                    if self.windows.grabbing:
                        self.windows.end_move()
                self.activity.add(gesture, "Emergency stop - all gesture actions disabled")
                self.notify("emergency_stop", {"source": "gesture"})
            elif kind == Ev.RESUME:
                # The state machine already reset itself; only the cursor filter needs a fresh start.
                self.cursor.reset()
                self._pending_click_pos = None
                self.activity.add(gesture, "Resumed after emergency stop")
                self.notify("resumed", {})
        except Exception as exc:
            self.activity.add(gesture, kind.replace("_", " "), success=False, error=str(exc))
            if kind == Ev.WINDOW_MOVE:
                self.windows.end_move()

    def _move_to_pending(self) -> None:
        if self._pending_click_pos is not None:
            if self.mouse.position() != self._pending_click_pos:
                self.mouse.move(*self._pending_click_pos)
            self._pending_click_pos = None

    # window helpers ----------------------------------------------------------------------
    def _window_grab_start(self, gesture: str) -> None:
        target = self.window_cfg.get("target", "active")
        if self.window_cfg.get("mode", "direct") == "titlebar":
            info = self.windows.target(target)
            x, y = self.windows.title_bar_point(info)
            self.mouse.move(x, y)
            self.mouse.down("left")
            self._titlebar_start = (x, y)
            self.activity.add(gesture, f"Grabbed title bar of '{info.title}'")
        else:
            info = self.windows.begin_move(target)
            self.activity.add(gesture, f"Grabbed window '{info.title}'")

    def _window_move(self, dx: float, dy: float) -> None:
        gx, gy = self.cursor.gain()
        gain = float(self.window_cfg.get("gain", 1.0))
        px, py = int(dx * gx * gain), int(dy * gy * gain)
        if self._titlebar_start is not None:
            self.mouse.move(self._titlebar_start[0] + px, self._titlebar_start[1] + py)
        elif self.windows.grabbing:
            self.windows.move_by(px, py)

    def _window_grab_end(self, gesture: str) -> None:
        if self._titlebar_start is not None:
            self._titlebar_start = None
            self.mouse.up("left")
            self.activity.add(gesture, "Window released")
            return
        info = self.windows.end_move()
        if info is not None:
            self.activity.add(gesture, f"Released window '{info.title}'")

    def _window_command(self, event: Event) -> None:
        action = event.data["action"]
        gesture = TRIGGER_GESTURE.get(event.data.get("trigger", ""), "Window gesture")
        target = self.window_cfg.get("target", "active")
        if action == "empty_recycle_bin":
            self._ask_empty_recycle_bin(gesture)
            return
        if action == "close" and event.data.get("dialog"):
            info = self.windows.target(target)
            if info.pid == self.windows.own_pid:
                raise WindowError("Refusing to close Hand Gesture Mouse itself with a gesture")
            self.activity.add(gesture, f"Asking to confirm closing '{info.title}'")
            self.notify("confirm_close", {"hwnd": info.hwnd, "title": info.title})
            return
        message = self.windows.command(action, target)
        self.activity.add(gesture, message)


    def _ask_empty_recycle_bin(self, gesture: str) -> None:
        """Deleting is permanent: never empty directly, ask the GUI to confirm first."""
        items, size = self.bin_query()
        if items == 0:
            self.activity.add(gesture, "Recycle Bin is already empty")
            self.notify("recycle_bin_empty", {})
            return
        self.activity.add(gesture, f"Asking to confirm emptying the Recycle Bin ({items} items)")
        self.notify("confirm_empty_bin", {"items": items, "bytes": size})


def pose_label(pose: Pose) -> str:
    return POSE_LABELS.get(pose, pose.value)
