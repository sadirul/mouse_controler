"""End-to-end GUI smoke test with the real camera and tracking thread.

Gesture control is paused before the first frame is processed, so this never moves the mouse.
    python tools/smoke_gui.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["HGM_DATA_DIR"] = tempfile.mkdtemp(prefix="hgm_smoke_")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.logger import ActivityLog, setup_logging
from app.settings_manager import SettingsManager
from ui import theme
from ui.main_window import MainWindow

setup_logging()
app = QApplication(sys.argv)
app.setStyleSheet(theme.STYLE)
win = MainWindow(SettingsManager(), ActivityLog())
win.show()
stats = {"frames": 0, "status": None, "camera": []}


def start():
    win.start_tracking()
    win.toggle_pause()  # queued before the worker processes its first frame
    win.worker.frame_ready.connect(lambda _img: stats.__setitem__("frames", stats["frames"] + 1))
    win.worker.status.connect(lambda s: stats.__setitem__("status", s))
    win.worker.camera_state.connect(lambda s, m: stats["camera"].append(s))


def exercise():
    for i in range(win.stack.count()):  # visit every page while tracking runs
        win.stack.setCurrentIndex(i)
        app.processEvents()
    win.settings.set("cursor.smoothing", 0.7)  # live settings change while tracking
    win.settings.set("camera.mirror", False)  # forces a camera restart
    win.stack.setCurrentIndex(0)


def finish():
    s = stats["status"] or {}
    print("frames received:", stats["frames"])
    print("camera states:", stats["camera"])
    print("fps:", s.get("fps"), "| mouse:", s.get("mouse"), "| mode:", s.get("mode"))
    print("paused:", win.paused, "| worker running:", win.worker is not None)
    win.quit()


QTimer.singleShot(300, start)
QTimer.singleShot(5000, exercise)
QTimer.singleShot(10000, finish)
code = app.exec()
print("exit code", code, "| worker after quit:", win.worker is None or not win.worker.isRunning())
