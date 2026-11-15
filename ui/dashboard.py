"""Main dashboard: live preview, status tiles and tracking controls."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from app.hotkeys import pretty
from ui import theme
from ui.widgets import Card, StatusTile, page_header

FINGER_COLORS = {"extended": theme.OK, "partial": theme.WARN, "folded": theme.MUTED}


class PreviewLabel(QLabel):
    """Keeps the camera image scaled to the available space without growing the layout."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Preview")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(QSize(400, 300))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._image: QImage | None = None

    def set_image(self, image: QImage | None) -> None:
        self._image = image
        self._refresh()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._image is None or self._image.isNull():
            self.setPixmap(QPixmap())
            return
        pix = QPixmap.fromImage(self._image).scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(pix)


class Banner(QFrame):
    action = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 10, 10)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.button = QPushButton()
        self.button.clicked.connect(self.action.emit)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.button)
        self.hide()

    def show_message(self, text: str, color: str, button: str | None = None) -> None:
        self.setStyleSheet(f"QFrame#Banner {{ background: {theme.rgba(color, 0.13)}; border: 1px solid {color}; }}"
                           f"QLabel {{ color: {theme.TEXT}; font-weight: 600; }}")
        self.text.setText(text)
        self.button.setVisible(bool(button))
        if button:
            self.button.setText(button)
        self.show()


class DashboardPage(QWidget):
    start_requested = Signal()
    stop_requested = Signal()
    pause_toggled = Signal()
    emergency_requested = Signal()
    resume_requested = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        root.addWidget(page_header("Dashboard", "Live hand tracking and gesture control status."))

        self.banner = Banner()
        self.banner.action.connect(self.resume_requested.emit)
        root.addWidget(self.banner)

        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)

        # ---- preview -------------------------------------------------------------
        preview_card = Card("Live camera")
        self.preview = PreviewLabel()
        self.preview.setText("Camera is off\n\nPress  Start tracking  to begin")
        preview_card.add(self.preview, 1)
        fingers = QHBoxLayout()
        fingers.setSpacing(6)
        self.finger_chips: dict[str, QLabel] = {}
        for name in ("thumb", "index", "middle", "ring", "pinky"):
            chip = QLabel(name.capitalize())
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setToolTip("Finger state: green = extended, amber = partially bent, grey = folded")
            self.finger_chips[name] = chip
            fingers.addWidget(chip)
        preview_card.add_layout(fingers)
        self.hold_bar = QProgressBar()
        self.hold_bar.setRange(0, 100)
        self.hold_bar.setTextVisible(False)
        self.hold_bar.setFixedHeight(8)
        self.hold_label = QLabel(" ")
        self.hold_label.setObjectName("Small")
        preview_card.add(self.hold_label)
        preview_card.add(self.hold_bar)
        body.addWidget(preview_card, 3)

        # ---- right column -----------------------------------------------------------
        right = QVBoxLayout()
        right.setSpacing(16)
        body.addLayout(right, 2)

        status = Card("Status")
        grid = QGridLayout()
        grid.setSpacing(10)
        self.tiles = {
            "camera": StatusTile("Camera", "Disconnected"),
            "hand": StatusTile("Hand detection", "-"),
            "fps": StatusTile("Tracking FPS", "-"),
            "controlling": StatusTile("Controlling hand", "-"),
            "gesture": StatusTile("Current gesture", "-"),
            "mouse": StatusTile("Mouse control", "Off"),
            "mode": StatusTile("Active mode", "-"),
            "cursor": StatusTile("Cursor", "-"),
        }
        for i, tile in enumerate(self.tiles.values()):
            grid.addWidget(tile, i // 2, i % 2)
        status.add_layout(grid)
        right.addWidget(status)

        controls = Card("Controls")
        row1 = QHBoxLayout()
        self.start_btn = QPushButton("Start tracking")
        self.start_btn.setObjectName("Primary")
        self.stop_btn = QPushButton("Stop tracking")
        self.pause_btn = QPushButton("Pause")
        for b in (self.start_btn, self.stop_btn, self.pause_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(38)
            row1.addWidget(b)
        controls.add_layout(row1)
        self.emergency_btn = QPushButton("EMERGENCY STOP")
        self.emergency_btn.setObjectName("Danger")
        self.emergency_btn.setMinimumHeight(46)
        self.emergency_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        controls.add(self.emergency_btn)
        self.hotkey_hint = QLabel()
        self.hotkey_hint.setObjectName("Small")
        self.hotkey_hint.setWordWrap(True)
        controls.add(self.hotkey_hint)
        right.addWidget(controls)
        right.addStretch(1)

        self.start_btn.clicked.connect(self.start_requested.emit)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.pause_btn.clicked.connect(self.pause_toggled.emit)
        self.emergency_btn.clicked.connect(self._emergency_clicked)

        self._stopped = False
        self.set_tracking(False)
        self.refresh_hotkeys()
        self._set_fingers({})

    # ------------------------------------------------------------------ state updates
    def refresh_hotkeys(self) -> None:
        if self.settings.get("app.hotkeys_enabled"):
            self.hotkey_hint.setText(
                f"Global hotkeys: pause/resume {pretty(self.settings.get('app.hotkey_pause'))} · "
                f"emergency stop {pretty(self.settings.get('app.hotkey_emergency'))} · "
                f"resume {pretty(self.settings.get('app.hotkey_resume'))}.  "
                f"Gesture: hold an open palm for {self.settings.get('gestures.emergency_stop.hold_ms') / 1000:.1f} s"
                + (f"; resume by holding a {self.settings.get('gestures.resume.pose')} for "
                   f"{self.settings.get('gestures.resume.hold_ms') / 1000:.1f} s."
                   if self.settings.get('gestures.resume.enabled') else "."))
        else:
            self.hotkey_hint.setText("Global hotkeys are disabled (Settings).")

    def _emergency_clicked(self) -> None:
        if self._stopped:
            self.resume_requested.emit()
        else:
            self.emergency_requested.emit()

    def set_tracking(self, running: bool, starting: bool = False) -> None:
        self.start_btn.setEnabled(not running and not starting)
        self.start_btn.setText("Starting..." if starting else "Start tracking")
        self.stop_btn.setEnabled(running)
        self.pause_btn.setEnabled(running)
        if not running:
            self.preview.set_image(None)
            self.preview.setText("Camera is off\n\nPress  Start tracking  to begin")
            for key in ("hand", "fps", "gesture", "mode", "cursor"):
                self.tiles[key].set_value("-")
            self.tiles["mouse"].set_value("Off", theme.MUTED)
            self.hold_bar.setValue(0)
            self.hold_label.setText(" ")
            self._set_fingers({})

    def set_paused(self, paused: bool) -> None:
        self.pause_btn.setText("Resume" if paused else "Pause")
        self.pause_btn.setObjectName("Warn" if paused else "")
        self.pause_btn.style().unpolish(self.pause_btn)
        self.pause_btn.style().polish(self.pause_btn)

    def set_stopped(self, stopped: bool) -> None:
        self._stopped = stopped
        if stopped:
            self.emergency_btn.setText("RESUME CONTROL")
            self.emergency_btn.setObjectName("Primary")
            self.banner.show_message("Emergency stop is active - all mouse and window actions are disabled.",
                                     theme.DANGER, "Resume control")
        else:
            self.emergency_btn.setText("EMERGENCY STOP")
            self.emergency_btn.setObjectName("Danger")
            self.banner.hide()
        self.emergency_btn.style().unpolish(self.emergency_btn)
        self.emergency_btn.style().polish(self.emergency_btn)

    def show_notice(self, text: str, color: str = theme.WARN) -> None:
        if not self._stopped:
            self.banner.show_message(text, color)

    def hide_notice(self) -> None:
        if not self._stopped:
            self.banner.hide()

    def set_camera(self, state: str, message: str) -> None:
        colors = {"connected": theme.OK, "connecting": theme.WARN, "error": theme.DANGER, "stopped": theme.MUTED}
        text = {"connected": "Connected", "connecting": "Connecting...", "error": "Error", "stopped": "Disconnected"}
        self.tiles["camera"].set_value(text.get(state, state), colors.get(state, theme.MUTED))
        self.tiles["camera"].setToolTip(message)
        if state == "error":
            self.preview.set_image(None)
            self.preview.setText(f"Camera error\n\n{message}")
        elif state == "connecting":
            self.preview.set_image(None)
            self.preview.setText("Opening camera...")

    def set_frame(self, image: QImage) -> None:
        self.preview.set_image(image)

    def update_status(self, s: dict) -> None:
        fps = s["fps"]
        self.tiles["fps"].set_value(f"{fps:.0f}", theme.OK if fps >= 20 else theme.WARN if fps >= 12 else theme.DANGER)
        self.tiles["hand"].set_value(s["hand"], theme.OK if s["hand_detected"] else theme.MUTED)
        self.tiles["controlling"].set_value(s["controlling_hand"], theme.ACCENT)
        self.tiles["gesture"].set_value(s["gesture"] or s["pose"], theme.ACCENT_2 if s["hand_detected"] else theme.MUTED)
        color = {"Active": theme.OK, "Paused": theme.WARN, "Emergency stop": theme.DANGER}.get(s["mouse"], theme.MUTED)
        self.tiles["mouse"].set_value(s["mouse"], color)
        self.tiles["mode"].set_value(s["mode"], theme.ACCENT)
        cur = s.get("cursor")
        self.tiles["cursor"].set_value(f"{cur[0]}, {cur[1]}" if cur else "-", theme.MUTED)
        self._set_fingers(s.get("fingers", {}))
        prog = s.get("progress", 0.0)
        self.hold_bar.setValue(int(prog * 100))
        self.hold_label.setText(f"{s.get('progress_label', '')}  {prog * 100:.0f}%" if prog > 0.02 else " ")

    def _set_fingers(self, fingers: dict) -> None:
        for name, chip in self.finger_chips.items():
            state = fingers.get(name)
            color = FINGER_COLORS.get(state, "#3a3f52")
            chip.setStyleSheet(
                f"QLabel {{ border: 1px solid {color}; border-radius: 9px; padding: 4px 6px; color: {color if state else theme.MUTED};"
                f" background: {theme.rgba(color, 0.12)}; font-size: 8.5pt; font-weight: 600; }}")
