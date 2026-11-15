"""Cursor mapping and smoothing settings."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.mouse_controller import list_monitors
from app.settings_manager import SettingsManager
from ui import theme
from ui.binding import Binder
from ui.widgets import Card, Row, SliderRow, page_header, scroll_page


class RegionPreview(QWidget):
    """Shows which part of the camera image maps onto the screen."""

    def __init__(self, settings: SettingsManager):
        super().__init__()
        self.settings = settings
        self.setFixedSize(240, 180)
        settings.add_listener(lambda path: self.update() if path.startswith("cursor") else None)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(QColor("#07080c"))
        p.drawRoundedRect(r, 10, 10)
        reg = self.settings.get("cursor.region")
        speed = self.settings.get("cursor.speed")
        cx, cy = (reg["left"] + reg["right"]) / 2, (reg["top"] + reg["bottom"]) / 2
        hw, hh = (reg["right"] - reg["left"]) / 2 / speed, (reg["bottom"] - reg["top"]) / 2 / speed
        eff = QRectF(r.left() + (cx - hw) * r.width(), r.top() + (cy - hh) * r.height(), 2 * hw * r.width(), 2 * hh * r.height())
        p.setPen(QPen(QColor(theme.ACCENT_2), 2))
        p.setBrush(QColor(34, 211, 238, 40))
        p.drawRoundedRect(eff, 6, 6)
        p.setPen(QColor(theme.MUTED))
        p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, "camera view")
        p.setPen(QColor(theme.ACCENT_2))
        p.drawText(eff, Qt.AlignmentFlag.AlignCenter, "= full screen")


class CursorSettingsPage(QWidget):
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.binder = Binder(settings, self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        head = QHBoxLayout()
        head.addWidget(page_header("Cursor", "How fingertip movement becomes cursor movement."), 1)
        reset = QPushButton("Reset cursor settings")
        reset.clicked.connect(self._reset)
        head.addWidget(reset, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)
        f2 = lambda v: f"{v:.2f}"  # noqa: E731

        motion = Card("Movement")
        self.mode = self.binder.combo(QComboBox(), "cursor.mode", [
            ("absolute", "Absolute - finger position = cursor position"),
            ("relative", "Relative - like a touchpad, with acceleration"),
        ])
        motion.add(Row("Cursor mode", self.mode, "Absolute is the most intuitive. Relative allows very precise "
                                                  "control: make a fist to reposition your hand without moving the cursor."))
        motion.add(self.binder.slider(SliderRow("Cursor speed", 0.5, 3.0, settings.get("cursor.speed"), 0.05,
                                                lambda v: f"{v:.2f}x"), "cursor.speed"))
        motion.add(self.binder.slider(SliderRow("Smoothing", 0.0, 1.0, settings.get("cursor.smoothing"), 0.01, f2,
                                                "Higher = steadier cursor when your hand is still."), "cursor.smoothing"))
        motion.add(self.binder.slider(SliderRow("Responsiveness", 0.0, 1.0, settings.get("cursor.responsiveness"), 0.01, f2,
                                                "Higher = less lag during fast movements."), "cursor.responsiveness"))
        self.accel = self.binder.slider(SliderRow("Acceleration (relative mode)", 0.0, 3.0, settings.get("cursor.acceleration"),
                                                  0.05, f2), "cursor.acceleration")
        motion.add(self.accel)
        motion.add(self.binder.slider(SliderRow("Dead zone", 0, 20, settings.get("cursor.dead_zone_px"), 1,
                                                lambda v: f"{v:.0f} px", "Ignore movements smaller than this."),
                                      "cursor.dead_zone_px", int))
        motion.add(self.binder.slider(SliderRow("Precision while pinching", 0.05, 1.0, settings.get("cursor.pinch_damping"), 0.05,
                                                lambda v: f"{v * 100:.0f}%",
                                                "Cursor speed while your thumb approaches the index finger, so clicks "
                                                "land where you aimed."), "cursor.pinch_damping"))
        lay.addWidget(motion)

        bounds = Card("Screen boundary mapping", "Only this part of the camera image is used. Your fingertip at the "
                                                 "edge of the box puts the cursor at the edge of the screen, so you never "
                                                 "have to move your hand out of view.")
        row = QHBoxLayout()
        sliders = QVBoxLayout()
        pct = lambda v: f"{v * 100:.0f}%"  # noqa: E731
        for key, lo, hi in (("left", 0.0, 0.45), ("right", 0.55, 1.0), ("top", 0.0, 0.45), ("bottom", 0.55, 1.0)):
            sliders.addWidget(self.binder.slider(SliderRow(f"{key.capitalize()} edge", lo, hi,
                                                           settings.get(f"cursor.region.{key}"), 0.01, pct),
                                                 f"cursor.region.{key}"))
        row.addLayout(sliders, 1)
        row.addWidget(RegionPreview(settings))
        bounds.add_layout(row)
        lay.addWidget(bounds)

        mon = Card("Monitors")
        options = [("all", "All monitors (whole virtual desktop)"), ("primary", "Primary monitor only")]
        for i, m in enumerate(list_monitors()):
            options.append((str(i), f"Monitor {i + 1}: {m.width}x{m.height} at ({m.left}, {m.top})"
                                    + (" - primary" if i == 0 else "")))
        mon.add(Row("Cursor area", self.binder.combo(QComboBox(), "cursor.monitor", options),
                    f"{len(options) - 2} monitor(s) detected."))
        lay.addWidget(mon)
        lay.addStretch()
        outer.addWidget(scroll_page(content))

        self.mode.currentIndexChanged.connect(self._mode_changed)
        self._mode_changed()

    def _mode_changed(self, *_):
        self.accel.setEnabled(self.settings.get("cursor.mode") == "relative")

    def _reset(self) -> None:
        self.settings.reset("cursor")
        self.binder.refresh_all()
        self._mode_changed()
