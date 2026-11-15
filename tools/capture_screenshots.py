"""Render screenshots of every application page using a synthetic hand (no real camera image).

    python tools/capture_screenshots.py [output_dir]
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["HGM_DATA_DIR"] = tempfile.mkdtemp(prefix="hgm_shots_")  # never touch the user's settings

import cv2
import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.cursor_controller import CursorController, Rect
from app.gesture_state import State
from app.logger import ActivityLog
from app.overlay import draw_overlay
from app.settings_manager import SettingsManager
from app.simulation import pose_landmarks
from ui import theme
from ui.main_window import MainWindow

out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "assets" / "screenshots"
out.mkdir(parents=True, exist_ok=True)

app = QApplication(sys.argv)
app.setStyle("Fusion")
app.setPalette(theme.palette())
app.setStyleSheet(theme.STYLE)
settings = SettingsManager()
activity = ActivityLog()
for g, a, ok, err in [
    ("Tracking", "Started", True, ""), ("Thumb + index pinch", "Left click", True, ""),
    ("Two quick pinches", "Double click", True, ""), ("Thumb + middle pinch", "Right click", True, ""),
    ("Hold / move pinch", "Drag started", True, ""), ("Release pinch", "Drop / button released", True, ""),
    ("Three fingers", "Grabbed window 'Notepad'", True, ""), ("Three fingers released", "Released window 'Notepad'", True, ""),
    ("Four-finger swipe up", "Maximized 'Notepad'", True, ""),
    ("Thumb + pinky hold", "Close armed - repeat the gesture to confirm", True, ""),
    ("Thumb + pinky hold", "close", False, "'Program Manager' is a protected system window"),
    ("Open palm (hold)", "Emergency stop - all gesture actions disabled", True, ""),
]:
    activity.add(g, a, ok, err)
win = MainWindow(settings, activity)
win.resize(1320, 860)
win.show()


def synthetic_frame(pose: str, state: State, label: str, center=(0.52, 0.86)) -> QImage:
    h, w = 480, 640
    y = np.linspace(0, 1, h)[:, None, None]
    frame = (np.array([38, 30, 26]) * (1 - y) + np.array([70, 58, 52]) * y).astype(np.uint8)
    frame = np.repeat(frame, w, axis=1).copy()
    cv2.rectangle(frame, (430, 60), (600, 300), (90, 80, 72), -1)
    cv2.rectangle(frame, (40, 330), (260, 480), (60, 52, 48), -1)
    lm = pose_landmarks(pose, center=center, size=0.30)
    region = CursorController(Rect(0, 0, 1920, 1080), settings.get("cursor")).effective_region()
    draw_overlay(frame, lm, state, label, 0.97, region)
    return QImage(frame.data, w, h, frame.strides[0], QImage.Format.Format_BGR888).copy()


def shoot():
    d = win.dashboard
    d.set_tracking(True)
    d.set_camera("connected", "Camera 0 - 640x480")
    d.set_frame(synthetic_frame("point", State.POINTING, "Move cursor"))
    d.update_status({"fps": 29, "hand_detected": True, "hand": "Right hand (97%)", "controlling_hand": "Right",
                     "pose": "Index pointer", "gesture": "Move cursor", "mode": "Cursor control", "mouse": "Active",
                     "cursor": (1184, 506), "fingers": {"thumb": "folded", "index": "extended", "middle": "folded",
                                                       "ring": "folded", "pinky": "folded"},
                     "progress": 0.0, "progress_label": ""})
    win.worker = object()  # pretend tracking runs so controls render as active
    win._update_controls()
    win.worker = None
    pages = ["dashboard", "gestures", "camera", "cursor", "activity_logs", "settings"]
    for i, name in enumerate(pages):
        win.stack.setCurrentIndex(i)
        win.nav.button(i).setChecked(True)
        app.processEvents()
        win.grab().save(str(out / f"{name}.png"))
    # dashboard variants
    win.stack.setCurrentIndex(0)
    win.nav.button(0).setChecked(True)
    d.set_frame(synthetic_frame("pinch_index", State.DRAGGING, "Dragging"))
    d.update_status({"fps": 28, "hand_detected": True, "hand": "Right hand (96%)", "controlling_hand": "Right",
                     "pose": "Thumb + index pinch", "gesture": "Dragging", "mode": "Drag / long press", "mouse": "Active",
                     "cursor": (902, 433), "fingers": {"thumb": "extended", "index": "partial", "middle": "folded",
                                                      "ring": "folded", "pinky": "folded"},
                     "progress": 0.0, "progress_label": ""})
    app.processEvents()
    win.grab().save(str(out / "dashboard_drag.png"))
    d.set_frame(synthetic_frame("open_palm", State.STOPPED, "Emergency stop"))
    d.set_stopped(True)
    d.update_status({"fps": 29, "hand_detected": True, "hand": "Right hand (98%)", "controlling_hand": "Right",
                     "pose": "Open palm", "gesture": "Emergency stop", "mode": "Emergency stop", "mouse": "Emergency stop",
                     "cursor": (902, 433), "fingers": {k: "extended" for k in ("thumb", "index", "middle", "ring", "pinky")},
                     "progress": 1.0, "progress_label": "Emergency stop"})
    app.processEvents()
    win.grab().save(str(out / "dashboard_emergency.png"))
    print("screenshots written to", out)
    win._quitting = True
    win.hotkeys.stop()
    app.quit()


QTimer.singleShot(600, shoot)
app.exec()
