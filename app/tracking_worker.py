"""Background tracking thread: camera -> MediaPipe -> gestures -> OS actions -> preview.

All heavy work happens here so the Qt GUI thread never blocks. The GUI talks to the worker through
a thread-safe command queue; the worker reports back with Qt signals (delivered on the GUI thread).
"""
from __future__ import annotations

import logging
import queue
import time
from typing import Any

import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from app.camera_manager import CameraError, CameraManager
from app.gesture_controller import GestureController, pose_label
from app.gesture_state import State
from app.hand_tracker import HandTracker, HandTrackerError, select_hand
from app.logger import ActivityLog
from app.mouse_controller import MouseController, target_screen
from app.overlay import draw_overlay
from app.paths import model_path
from app.settings_manager import SettingsManager
from app.window_controller import WindowController

log = logging.getLogger(__name__)

STATE_MODES = {
    State.IDLE: "Idle",
    State.POINTING: "Cursor control",
    State.PINCH: "Click / press",
    State.DRAGGING: "Drag / long press",
    State.WAIT_RELEASE: "Waiting for release",
    State.RIGHT_PINCH: "Right click",
    State.SCROLLING: "Scrolling",
    State.WINDOW_MOVING: "Window move",
    State.SWIPE: "Window swipe",
    State.HOLD_POSE: "Window command",
    State.STOPPED: "Emergency stop",
}


class TrackingWorker(QThread):
    frame_ready = Signal(QImage)
    status = Signal(dict)
    camera_state = Signal(str, str)  # state: connecting | connected | error | stopped ; message
    notice = Signal(str, dict)  # emergency_stop | resumed | close_armed | close_cancelled | confirm_close
    fatal_error = Signal(str)

    def __init__(self, settings: SettingsManager, activity: ActivityLog, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.activity = activity
        self._commands: queue.Queue = queue.Queue()
        self._running = False
        self.preview_enabled = True
        self.paused = False
        self.stopped = False

    # ------------------------------------------------------------------ GUI-thread API
    def request_stop(self) -> None:
        self._running = False

    def pause(self) -> None:
        self.paused = True
        self._commands.put(("pause",))

    def resume(self) -> None:
        self.paused = False
        self._commands.put(("resume",))

    def emergency_stop(self, source: str = "Button") -> None:
        self.stopped = True
        self._commands.put(("emergency", source))

    def resume_from_stop(self) -> None:
        self.stopped = False
        self._commands.put(("resume_stop",))

    def close_window(self, hwnd: int) -> None:
        self._commands.put(("close_window", hwnd))

    # ------------------------------------------------------------------ thread body
    def run(self) -> None:  # noqa: C901 - the main loop is intentionally linear
        self._running = True
        cfg = self.settings.snapshot()
        version = self.settings.version
        camera: CameraManager | None = None
        tracker: HandTracker | None = None
        controller: GestureController | None = None
        try:
            try:
                tracker = self._make_tracker(cfg)
            except HandTrackerError as exc:
                self.fatal_error.emit(str(exc))
                self.activity.add("Tracking", "Start MediaPipe", success=False, error=str(exc))
                return

            controller = GestureController(
                cfg, MouseController(), WindowController(), self.activity,
                target_screen(cfg["cursor"]["monitor"]), notify=self._notify,
            )
            if self.paused:
                controller.pause()
            camera = self._open_camera(cfg)
            if camera is None:
                return
            self.activity.add("Tracking", "Started")

            frame_times: list[float] = []
            last_status = 0.0
            last_screen_check = time.monotonic()
            last_preview = 0.0
            controlling: str | None = None  # handedness of the hand currently in control
            while self._running:
                loop_start = time.monotonic()
                self._drain_commands(controller)

                # Settings changed in the GUI?
                if self.settings.version != version:
                    new_cfg = self.settings.snapshot()
                    version = self.settings.version
                    camera_changed = new_cfg["camera"] != cfg["camera"]
                    tracking_changed = {k: v for k, v in new_cfg["tracking"].items() if k.startswith("min_") and k != "min_hand_score"} != \
                        {k: v for k, v in cfg["tracking"].items() if k.startswith("min_") and k != "min_hand_score"}
                    cfg = new_cfg
                    controller.configure(cfg)
                    controller.set_screen(target_screen(cfg["cursor"]["monitor"]))
                    if tracking_changed:
                        tracker.close()
                        tracker = self._make_tracker(cfg)
                    if camera_changed:
                        camera.release()
                        camera = self._open_camera(cfg)
                        if camera is None:
                            return
                if loop_start - last_screen_check > 3.0:  # monitors plugged / unplugged
                    last_screen_check = loop_start
                    screen = target_screen(cfg["cursor"]["monitor"])
                    if screen != controller.cursor.screen:
                        controller.set_screen(screen)

                try:
                    frame = camera.read()
                except CameraError as exc:
                    controller.shutdown()
                    self.camera_state.emit("error", str(exc))
                    self.activity.add("Camera", "Read frame", success=False, error=str(exc))
                    return
                if frame is None:
                    continue

                h, w = frame.shape[:2]
                mirrored = bool(cfg["camera"]["mirror"])
                hands = tracker.process(frame, mirrored=mirrored)
                hand = select_hand(hands, cfg["tracking"]["preferred_hand"], cfg["tracking"]["min_hand_score"],
                                   previous=controlling)
                now = time.monotonic()
                if hand is not None:
                    if controlling is not None and hand.handedness != controlling:
                        controller.switch_hand()
                        self.activity.add("Tracking", f"Control switched to {hand.handedness.lower()} hand")
                    controlling = hand.handedness
                min_score = cfg["tracking"]["min_hand_score"]
                others = [h_ for h_ in hands if h_ is not hand and h_.score >= min_score]
                result = controller.process(hand, now, aspect=w / h, mirrored=mirrored, others=others)

                frame_times.append(now)
                frame_times = [t for t in frame_times if now - t <= 1.0]
                fps = float(len(frame_times))

                if self.preview_enabled and now - last_preview >= 1 / 30:
                    last_preview = now
                    d = result.decision
                    label = d.label if not controller.paused else "Paused"
                    other_landmarks = [h_.landmarks for h_ in hands if h_ is not hand]
                    draw_overlay(
                        frame, hand.landmarks if hand else None, d.state, label,
                        hand.score if hand else None, controller.cursor.effective_region(),
                        d.progress, d.progress_label, controller.paused, other_landmarks,
                    )
                    image = QImage(frame.data, w, h, frame.strides[0], QImage.Format.Format_BGR888).copy()
                    self.frame_ready.emit(image)

                if now - last_status >= 0.1:
                    last_status = now
                    self.status.emit(self._status(result, hand, hands, fps, controller, cfg))

                max_fps = float(cfg["tracking"]["max_fps"])
                spare = (1.0 / max_fps) - (time.monotonic() - loop_start)
                if spare > 0:
                    time.sleep(spare)
        except Exception as exc:  # pragma: no cover - last-resort safety net
            log.exception("Tracking loop crashed")
            self.fatal_error.emit(f"Tracking stopped because of an unexpected error: {exc}")
            self.activity.add("Tracking", "Tracking loop", success=False, error=str(exc))
        finally:
            if controller is not None:
                controller.shutdown()  # releases held mouse buttons / window grabs
            if camera is not None:
                camera.release()
            if tracker is not None:
                tracker.close()
            self.camera_state.emit("stopped", "Camera released")
            self.activity.add("Tracking", "Stopped")

    # ------------------------------------------------------------------ helpers
    def _make_tracker(self, cfg: dict[str, Any]) -> HandTracker:
        t = cfg["tracking"]
        return HandTracker(
            str(model_path()),
            num_hands=2,
            min_detection_confidence=t["min_detection_confidence"],
            min_presence_confidence=t["min_presence_confidence"],
            min_tracking_confidence=t["min_tracking_confidence"],
        )

    def _open_camera(self, cfg: dict[str, Any]) -> CameraManager | None:
        c = cfg["camera"]
        camera = CameraManager(c["device"], c["width"], c["height"], c["fps"], c["mirror"])
        self.camera_state.emit("connecting", f"Opening camera {c['device']}...")
        try:
            camera.open()
        except CameraError as exc:
            self.camera_state.emit("error", str(exc))
            self.activity.add("Camera", f"Open camera {c['device']}", success=False, error=str(exc))
            return None
        w, h = camera.actual_size
        self.camera_state.emit("connected", f"Camera {c['device']} - {w}x{h}")
        return camera

    def _drain_commands(self, controller: GestureController) -> None:
        while True:
            try:
                cmd = self._commands.get_nowait()
            except queue.Empty:
                return
            name = cmd[0]
            if name == "pause":
                controller.pause()
            elif name == "resume":
                controller.resume()
            elif name == "emergency":
                controller.emergency_stop(cmd[1])
            elif name == "resume_stop":
                controller.resume_from_stop()
            elif name == "close_window":
                try:
                    msg = controller.windows.close_window(cmd[1])
                    self.activity.add("Close confirmed", msg)
                except Exception as exc:
                    self.activity.add("Close confirmed", "Close window", success=False, error=str(exc))

    def _notify(self, kind: str, data: dict) -> None:
        if kind == "emergency_stop":
            self.stopped = True
        elif kind == "resumed":
            self.stopped = False
        self.notice.emit(kind, data)

    def _status(self, result, hand, hands, fps, controller: GestureController, cfg) -> dict:
        d = result.decision
        if controller.stopped:
            mouse = "Emergency stop"
        elif controller.paused:
            mouse = "Paused"
        else:
            mouse = "Active"
        if hand is not None:
            hand_text = f"{hand.handedness} hand ({hand.score * 100:.0f}%)"
        elif hands:
            hand_text = f"{hands[0].handedness} hand - not the controlling hand"
        else:
            hand_text = "No hand detected"
        return {
            "fps": fps,
            "hand_detected": hand is not None,
            "hand": hand_text,
            "controlling_hand": {"right": "Right", "left": "Left"}.get(cfg["tracking"]["preferred_hand"], "Either"),
            "pose": pose_label(result.pose),
            "gesture": d.label,
            "mode": STATE_MODES.get(d.state, d.state.value) if not controller.paused else "Paused",
            "mouse": mouse,
            "cursor": result.cursor,
            "fingers": {k: v.value for k, v in result.features.fingers.items()} if result.features else {},
            "progress": d.progress,
            "progress_label": d.progress_label,
        }
