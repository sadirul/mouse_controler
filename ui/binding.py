"""Bind settings widgets to dotted settings paths with debounced saving."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QComboBox

from app.settings_manager import SettingsManager
from ui.widgets import SliderRow, ToggleSwitch


class Binder(QObject):
    """Writes changes into the SettingsManager immediately (so tracking reacts live) and saves the
    JSON files shortly after the user stops dragging a slider."""

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self.settings.save)
        self._refreshers: list = []

    def set(self, path: str, value: Any) -> None:
        self.settings.set(path, value, save=False)
        self._timer.start()

    def slider(self, row: SliderRow, path: str, cast=float) -> SliderRow:
        row.set_value(float(self.settings.get(path)))
        row.valueChanged.connect(lambda v: self.set(path, cast(round(v)) if cast is int else cast(v)))
        self._refreshers.append(lambda: row.set_value(float(self.settings.get(path))))
        return row

    def toggle(self, switch: ToggleSwitch, path: str) -> ToggleSwitch:
        switch.setChecked(bool(self.settings.get(path)))
        switch.toggled.connect(lambda v: self.set(path, bool(v)))

        def refresh():
            switch.blockSignals(True)
            switch.setChecked(bool(self.settings.get(path)))
            switch.blockSignals(False)

        self._refreshers.append(refresh)
        return switch

    def combo(self, combo: QComboBox, path: str, options: list[tuple[Any, str]]) -> QComboBox:
        for value, label in options:
            combo.addItem(label, value)

        def refresh():
            current = self.settings.get(path)
            idx = combo.findData(current)
            combo.blockSignals(True)
            combo.setCurrentIndex(max(idx, 0))
            combo.blockSignals(False)

        refresh()
        combo.currentIndexChanged.connect(lambda _i: self.set(path, combo.currentData()))
        self._refreshers.append(refresh)
        return combo

    def refresh_all(self) -> None:
        for refresh in self._refreshers:
            refresh()
