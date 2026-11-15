"""Reusable widgets: cards, status tiles, toggle switches, labelled sliders."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from ui import theme


class Card(QFrame):
    def __init__(self, title: str | None = None, subtitle: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(18, 16, 18, 16)
        self.layout_.setSpacing(10)
        if title:
            t = QLabel(title)
            t.setObjectName("CardTitle")
            self.layout_.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("Muted")
            s.setWordWrap(True)
            self.layout_.addWidget(s)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.layout_.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout) -> None:
        self.layout_.addLayout(layout)


class StatusTile(QFrame):
    """Small tile with a coloured indicator dot, a caption and a value."""

    def __init__(self, label: str, value: str = "-", parent=None):
        super().__init__(parent)
        self.setObjectName("Tile")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        top = QHBoxLayout()
        self.dot = QLabel()
        self.dot.setFixedSize(9, 9)
        self.caption = QLabel(label.upper())
        self.caption.setObjectName("TileLabel")
        top.addWidget(self.dot)
        top.addWidget(self.caption)
        top.addStretch()
        lay.addLayout(top)
        self.value = QLabel(value)
        self.value.setObjectName("TileValue")
        self.value.setWordWrap(True)
        lay.addWidget(self.value)
        self.set_value(value)

    def set_value(self, value: str, color: str = theme.MUTED) -> None:
        if self.value.text() != value:
            self.value.setText(value)
        self.dot.setStyleSheet(f"background:{color}; border-radius:4px;")


class ToggleSwitch(QAbstractButton):
    """iOS-style animated switch."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(42, 24)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def get_knob(self) -> float:
        return self._pos

    def set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, get_knob, set_knob)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt API
        super().setChecked(checked)
        self._pos = 1.0 if checked else 0.0
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height()).adjusted(1, 1, -1, -1)
        off, on = QColor(theme.BORDER), QColor(theme.ACCENT)
        track = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos),
        )
        if not self.isEnabled():
            track.setAlpha(90)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


class SliderRow(QWidget):
    """Label + slider + live value. Maps an integer slider onto a float range."""

    valueChanged = Signal(float)

    def __init__(self, label: str, minimum: float, maximum: float, value: float, step: float = 0.01,
                 fmt: Callable[[float], str] | None = None, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.minimum, self.maximum, self.step = minimum, maximum, step
        self.fmt = fmt or (lambda v: f"{v:.2f}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(label)
        self.label.setMinimumWidth(170)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, int(round((maximum - minimum) / step)))
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.value_label = QLabel()
        self.value_label.setMinimumWidth(70)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.label)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.value_label)
        if tooltip:
            self.setToolTip(tooltip)
        self.set_value(value)
        self.slider.valueChanged.connect(self._changed)

    def value(self) -> float:
        return round(self.minimum + self.slider.value() * self.step, 6)

    def set_value(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(round((value - self.minimum) / self.step)))
        self.slider.blockSignals(False)
        self.value_label.setText(self.fmt(self.value()))

    def _changed(self, _v: int) -> None:
        self.value_label.setText(self.fmt(self.value()))
        self.valueChanged.emit(self.value())


class Row(QWidget):
    """Label (with optional description) on the left, a control on the right."""

    def __init__(self, label: str, control: QWidget, description: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        text = QVBoxLayout()
        text.setSpacing(0)
        lbl = QLabel(label)
        text.addWidget(lbl)
        if description:
            d = QLabel(description)
            d.setObjectName("Small")
            d.setWordWrap(True)
            text.addWidget(d)
        lay.addLayout(text, 1)
        lay.addWidget(control, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.control = control


def page_header(title: str, subtitle: str) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 6)
    lay.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("PageTitle")
    s = QLabel(subtitle)
    s.setObjectName("PageSubtitle")
    s.setWordWrap(True)
    lay.addWidget(t)
    lay.addWidget(s)
    return w


def scroll_page(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(content)
    return area
