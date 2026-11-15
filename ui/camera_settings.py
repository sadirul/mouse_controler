"""Camera and hand-tracking settings, with camera scan and a camera test."""
from __future__ import annotations

import time

import cv2
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.camera_manager import CameraError, CameraManager, probe_cameras
from app.settings_manager import SettingsManager
from ui.binding import Binder
from ui.dashboard import PreviewLabel
from ui.widgets import Card, Row, SliderRow, ToggleSwitch, page_header, scroll_page

RESOLUTIONS = [(320, 240), (640, 480), (800, 600), (960, 540), (1280, 720), (1920, 1080)]


class ProbeThread(QThread):
    found = Signal(list)

    def __init__(self, skip: set[int]):
        super().__init__()
        self.skip = skip

    def run(self) -> None:
        self.found.emit(probe_cameras(6, self.skip))


class CameraTestThread(QThread):
    frame = Signal(QImage)
    result = Signal(bool, str)

    def __init__(self, cfg: dict, seconds: float = 6.0):
        super().__init__()
        self.cfg = cfg
        self.seconds = seconds
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        c = self.cfg
        cam = CameraManager(c["device"], c["width"], c["height"], c["fps"], c["mirror"])
        try:
            cam.open()
        except CameraError as exc:
            self.result.emit(False, str(exc))
            return
        frames = 0
        start = time.monotonic()
        try:
            while not self._stop and time.monotonic() - start < self.seconds:
                f = cam.read(timeout=1.0)
                if f is None:
                    continue
                frames += 1
                h, w = f.shape[:2]
                cv2.putText(f, f"Camera {c['device']}  {w}x{h}", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                self.frame.emit(QImage(f.data, w, h, f.strides[0], QImage.Format.Format_BGR888).copy())
            elapsed = time.monotonic() - start
            w, h = cam.actual_size
            self.result.emit(frames > 0, f"Camera works: {w}x{h} at {frames / max(elapsed, 0.01):.0f} FPS"
                             if frames else "The camera opened but delivered no frames")
        except CameraError as exc:
            self.result.emit(False, str(exc))
        finally:
            cam.release()


class CameraSettingsPage(QWidget):
    def __init__(self, settings: SettingsManager, is_tracking, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.is_tracking = is_tracking  # callable -> bool
        self.binder = Binder(settings, self)
        self._probe: ProbeThread | None = None
        self._test: CameraTestThread | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        lay.addWidget(page_header("Camera", "Choose the webcam and how hands are tracked. Camera changes restart "
                                            "the capture automatically while tracking runs."))

        cam = Card("Webcam")
        dev_row = QHBoxLayout()
        self.device = QComboBox()
        self.device.setMinimumWidth(240)
        self._fill_devices([{"index": settings.get("camera.device"), "label": f"Camera {settings.get('camera.device')}"}])
        self.device.currentIndexChanged.connect(self._device_changed)
        self.scan_btn = QPushButton("Scan for cameras")
        self.scan_btn.clicked.connect(self.scan)
        dev_row.addWidget(QLabel("Camera device"), 1)
        dev_row.addWidget(self.device)
        dev_row.addWidget(self.scan_btn)
        cam.add_layout(dev_row)

        self.resolution = QComboBox()
        for w, h in RESOLUTIONS:
            self.resolution.addItem(f"{w} x {h}", (w, h))
        current = (settings.get("camera.width"), settings.get("camera.height"))
        idx = self.resolution.findData(current)
        if idx < 0:
            self.resolution.addItem(f"{current[0]} x {current[1]}", current)
            idx = self.resolution.count() - 1
        self.resolution.setCurrentIndex(idx)
        self.resolution.currentIndexChanged.connect(self._resolution_changed)
        cam.add(Row("Resolution", self.resolution, "640 x 480 is recommended: higher resolutions cost CPU without "
                                                   "improving hand tracking."))
        self.fps = self.binder.combo(QComboBox(), "camera.fps", [(15, "15 FPS"), (24, "24 FPS"), (30, "30 FPS"), (60, "60 FPS")])
        cam.add(Row("Camera frame rate", self.fps))
        cam.add(Row("Mirror image", self.binder.toggle(ToggleSwitch(), "camera.mirror"),
                    "On for normal webcams (moving your hand right moves the cursor right). Turn off if your "
                    "camera already mirrors the image."))
        lay.addWidget(cam)

        track = Card("Hand tracking")
        track.add(Row("Controlling hand", self.binder.combo(QComboBox(), "tracking.preferred_hand",
                                                             [("any", "Either hand"), ("right", "Right hand"), ("left", "Left hand")]),
                      "Either hand: use your left or right hand. If both are visible, the hand that "
                      "was already in control keeps it. Right/Left: the other hand is ignored."))
        track.add(self.binder.slider(SliderRow("Max tracking FPS", 10, 60, settings.get("tracking.max_fps"), 1,
                                               lambda v: f"{v:.0f}"), "tracking.max_fps", int))
        track.add(self.binder.slider(SliderRow("Detection confidence", 0.3, 0.95, settings.get("tracking.min_detection_confidence"), 0.05,
                                               lambda v: f"{v:.2f}"), "tracking.min_detection_confidence"))
        track.add(self.binder.slider(SliderRow("Tracking confidence", 0.3, 0.95, settings.get("tracking.min_tracking_confidence"), 0.05,
                                               lambda v: f"{v:.2f}"), "tracking.min_tracking_confidence"))
        track.add(self.binder.slider(SliderRow("Min gesture confidence", 0.0, 0.95, settings.get("tracking.min_hand_score"), 0.05,
                                               lambda v: f"{v:.2f}",
                                               "Hands whose left/right confidence is below this are ignored."), "tracking.min_hand_score"))
        lay.addWidget(track)

        test = Card("Camera test", "Opens the selected camera for a few seconds to verify it works.")
        self.test_preview = PreviewLabel()
        self.test_preview.setMinimumSize(320, 240)
        self.test_preview.setMaximumHeight(300)
        self.test_preview.setText("No test running")
        test.add(self.test_preview)
        row = QHBoxLayout()
        self.test_btn = QPushButton("Test camera")
        self.test_btn.setObjectName("Primary")
        self.test_btn.clicked.connect(self.test_camera)
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        row.addWidget(self.test_btn)
        row.addWidget(self.test_result, 1)
        test.add_layout(row)
        lay.addWidget(test)
        lay.addStretch()
        outer.addWidget(scroll_page(content))

    # ------------------------------------------------------------------ devices
    def _fill_devices(self, devices: list[dict]) -> None:
        self.device.blockSignals(True)
        self.device.clear()
        current = self.settings.get("camera.device")
        if not any(d["index"] == current for d in devices):
            devices = [{"index": current, "label": f"Camera {current} (not found)"}] + devices
        for d in devices:
            self.device.addItem(d["label"], d["index"])
        self.device.setCurrentIndex(max(self.device.findData(current), 0))
        self.device.blockSignals(False)

    def scan(self) -> None:
        if self._probe is not None and self._probe.isRunning():
            return
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning...")
        skip = {self.settings.get("camera.device")} if self.is_tracking() else set()
        self._probe = ProbeThread(skip)
        self._probe.found.connect(self._scan_done)
        self._probe.start()

    def _scan_done(self, devices: list) -> None:
        self._fill_devices(devices)
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan for cameras")
        self.test_result.setText(f"Found {len(devices)} camera(s)." if devices else "No cameras found.")

    def _device_changed(self, _i: int) -> None:
        self.binder.set("camera.device", int(self.device.currentData()))

    def _resolution_changed(self, _i: int) -> None:
        w, h = self.resolution.currentData()
        self.settings.set("camera.width", int(w), save=False)
        self.binder.set("camera.height", int(h))

    # ------------------------------------------------------------------ test
    def test_camera(self) -> None:
        if self.is_tracking():
            self.test_result.setText("Tracking is running and using the camera - its live preview is on the "
                                     "Dashboard. Stop tracking to run a separate camera test.")
            return
        if self._test is not None and self._test.isRunning():
            self._test.stop()
            return
        self.test_btn.setText("Stop test")
        self.test_result.setText("Opening camera...")
        self._test = CameraTestThread(self.settings.snapshot()["camera"])
        self._test.frame.connect(self.test_preview.set_image)
        self._test.result.connect(self._test_done)
        self._test.start()

    def _test_done(self, ok: bool, message: str) -> None:
        self.test_btn.setText("Test camera")
        self.test_result.setText(("✔ " if ok else "✖ ") + message)
        self.test_preview.set_image(None)
        self.test_preview.setText("No test running")

    def shutdown(self) -> None:
        if self._test is not None and self._test.isRunning():
            self._test.stop()
            self._test.wait(3000)
        if self._probe is not None and self._probe.isRunning():
            self._probe.wait(5000)
