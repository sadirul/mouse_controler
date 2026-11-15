"""Built-in diagnostics: ``HandGestureMouse.exe --self-test``.

Checks every layer without moving the real mouse: settings storage, model file, MediaPipe,
camera capture + tracking speed, monitors, window API, and the gesture engine (driven by synthetic
hands against a recording fake mouse). Writes a report to logs/selftest.txt.
"""
from __future__ import annotations

import platform
import sys
import time
import traceback
from typing import Callable

from app import APP_NAME, __version__


class _FakeMouse:
    def __init__(self):
        self.pos = (500, 500)
        self.calls = []

    def move(self, x, y):
        self.pos = (x, y)

    def position(self):
        return self.pos

    def button(self, button, down):
        self.calls.append((button, down))

    def wheel(self, v, h):
        self.calls.append(("wheel", v, h))


def _gesture_engine() -> str:
    import copy

    from app.cursor_controller import Rect
    from app.gesture_controller import GestureController
    from app.hand_tracker import TrackedHand
    from app.logger import ActivityLog
    from app.mouse_controller import MouseController
    from app.settings_manager import DEFAULT_GESTURES, DEFAULT_SETTINGS
    from app.simulation import pose_landmarks
    from app.window_controller import WindowController

    cfg = copy.deepcopy(DEFAULT_SETTINGS)
    cfg.update(copy.deepcopy(DEFAULT_GESTURES))
    fake = _FakeMouse()
    ctl = GestureController(cfg, MouseController(fake), WindowController(), ActivityLog(), Rect(0, 0, 1920, 1080))
    t = [0.0]

    def hold(pose, ms, move=(0, 0)):
        n = max(1, round(ms / 1000 * 30))
        for i in range(n):
            c = (0.5 + move[0] * (i + 1) / n, 0.75 + move[1] * (i + 1) / n)
            t[0] += 1 / 30
            ctl.process(TrackedHand(pose_landmarks(pose, center=c), "Right", 0.95), t[0])

    hold("point", 300); hold("pinch_index", 120); hold("point", 600)
    clicks = sum(1 for c in fake.calls if c == ("left", False))
    hold("pinch_index", 100); hold("point", 130); hold("pinch_index", 100); hold("point", 600)
    dbl = sum(1 for c in fake.calls if c == ("left", False)) - clicks
    hold("pinch_middle", 300); hold("point", 300)
    right = sum(1 for c in fake.calls if c == ("right", False))
    hold("two_finger", 200); hold("two_finger", 400, move=(0, -0.15))
    scroll = sum(c[1] for c in fake.calls if c[0] == "wheel")
    hold("open_palm", 1800)
    stopped = ctl.stopped
    ok = clicks == 1 and dbl == 2 and right == 1 and scroll > 0 and stopped
    detail = f"click={clicks} double={dbl // 2} right={right} scroll_up={scroll:.1f} notches emergency_stop={stopped}"
    if not ok:
        raise AssertionError(detail)
    return detail


def run_checks(camera_seconds: float = 3.0) -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok_all = True

    def check(name: str, fn: Callable[[], str]) -> None:
        nonlocal ok_all
        try:
            detail = fn()
            lines.append(f"[ OK ] {name}: {detail}")
        except Exception as exc:  # noqa: BLE001 - report everything
            ok_all = False
            lines.append(f"[FAIL] {name}: {exc}")
            lines.append("       " + traceback.format_exc().strip().splitlines()[-1])

    lines.append(f"{APP_NAME} {__version__} self-test - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Python {sys.version.split()[0]} | {platform.platform()} | frozen={getattr(sys, 'frozen', False)}")

    def settings():
        from app.paths import config_dir
        from app.settings_manager import SettingsManager

        sm = SettingsManager()
        return f"{config_dir()} (camera {sm.get('camera.device')}, hand {sm.get('tracking.preferred_hand')})"

    def model():
        from app.paths import model_path

        p = model_path()
        if not p.exists():
            raise FileNotFoundError(p)
        return f"{p.name} {p.stat().st_size / 1e6:.1f} MB"

    tracker_holder = {}

    def mediapipe():
        import mediapipe as mp

        from app.hand_tracker import HandTracker
        from app.paths import model_path

        tracker_holder["t"] = HandTracker(str(model_path()))
        return f"mediapipe {mp.__version__} HandLandmarker ready"

    def camera():
        from app.camera_manager import CameraManager
        from app.settings_manager import SettingsManager

        c = SettingsManager().get("camera")
        cam = CameraManager(c["device"], c["width"], c["height"], c["fps"], c["mirror"])
        cam.open()
        tracker = tracker_holder.get("t")
        frames = hands = 0
        start = time.monotonic()
        try:
            while time.monotonic() - start < camera_seconds:
                f = cam.read(timeout=1.0)
                if f is None:
                    continue
                frames += 1
                if tracker is not None:
                    hands += bool(tracker.process(f))
        finally:
            cam.release()
        elapsed = time.monotonic() - start
        w, h = cam.actual_size
        return (f"camera {c['device']} {w}x{h}, {frames / elapsed:.1f} FPS with hand tracking, "
                f"hand visible in {hands}/{frames} frames")

    def monitors():
        from app.mouse_controller import list_monitors, virtual_screen

        mons = list_monitors()
        v = virtual_screen()
        return f"{len(mons)} monitor(s), virtual desktop {v.width}x{v.height} at ({v.left},{v.top})"

    def windows():
        from app.window_controller import WindowController

        wc = WindowController()
        if not wc.supported:
            return "window management not supported on this platform"
        info = wc.info(__import__("ctypes").windll.user32.GetForegroundWindow())
        return f"Win32 window API available (foreground: '{info.title[:40]}')"

    check("Settings storage", settings)
    check("Hand model", model)
    check("MediaPipe", mediapipe)
    check("Camera + tracking", camera)
    check("Monitors", monitors)
    check("Window API", windows)
    check("Gesture engine (synthetic hands, fake mouse)", _gesture_engine)
    if "t" in tracker_holder:
        tracker_holder["t"].close()
    lines.append("RESULT: " + ("ALL CHECKS PASSED" if ok_all else "SOME CHECKS FAILED"))
    return ok_all, lines


def main(show_dialog: bool = True) -> int:
    from app.logger import setup_logging
    from app.paths import log_dir

    setup_logging()
    if sys.platform == "win32":  # same coordinate space as the GUI (Qt is per-monitor DPI aware)
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            pass
    ok, lines = run_checks()
    report = "\n".join(lines)
    (log_dir() / "selftest.txt").write_text(report + "\n", encoding="utf-8")
    if sys.stdout is not None:
        print(report)
    if show_dialog:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841
        box = QMessageBox(QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning,
                          f"{APP_NAME} self-test", report)
        box.exec()
    return 0 if ok else 1
