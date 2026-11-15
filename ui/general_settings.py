"""Application settings: tray, background operation, start with Windows, hotkeys, maintenance."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from app import APP_NAME, __version__, autostart
from app.paths import config_dir, docs_index, log_dir
from app.settings_manager import SettingsManager
from ui.binding import Binder
from ui.widgets import Card, Row, ToggleSwitch, page_header, scroll_page


def open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 - opens a folder/file chosen by the app itself
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_docs() -> bool:
    path = docs_index()
    if not path.exists():
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class GeneralSettingsPage(QWidget):
    hotkeys_changed = Signal()
    settings_reset = Signal()

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
        lay.addWidget(page_header("Settings", "Background operation, startup and safety hotkeys."))

        bg = Card("Background operation")
        bg.add(Row("Minimize to system tray on close", self.binder.toggle(ToggleSwitch(), "app.minimize_to_tray"),
                   "The window's close button hides the app in the tray. Use Exit in the tray menu to quit."))
        bg.add(Row("Keep tracking in the background", self.binder.toggle(ToggleSwitch(), "app.background_tracking"),
                   "When off, gesture control pauses while the window is hidden in the tray."))
        bg.add(Row("Show camera preview", self.binder.toggle(ToggleSwitch(), "app.show_preview"),
                   "Turn off to save CPU. The preview is never rendered while the window is hidden."))
        lay.addWidget(bg)

        start = Card("Startup")
        self.autostart = ToggleSwitch(autostart.is_enabled())
        self.autostart.setEnabled(autostart.supported())
        self.autostart.toggled.connect(self._autostart_changed)
        start.add(Row("Start with Windows", self.autostart,
                      "Adds Hand Gesture Mouse to your Windows sign-in (current user only)." if autostart.supported()
                      else "Only available on Windows."))
        start.add(Row("Start minimized to tray", self.binder.toggle(ToggleSwitch(), "app.start_minimized")))
        start.add(Row("Start tracking automatically", self.binder.toggle(ToggleSwitch(), "app.auto_start_tracking"),
                      "Off by default for safety: the mouse is only controlled after you press Start."))
        lay.addWidget(start)

        keys = Card("Safety hotkeys", "System-wide shortcuts that work even when the window is hidden. "
                                      "Format: <ctrl>+<alt>+p (pynput syntax).")
        keys.add(Row("Enable global hotkeys", self.binder.toggle(ToggleSwitch(), "app.hotkeys_enabled")))
        self.key_edits: dict[str, QLineEdit] = {}
        for path, label in (("app.hotkey_pause", "Pause / resume"), ("app.hotkey_emergency", "Emergency stop"),
                            ("app.hotkey_resume", "Resume after emergency stop")):
            edit = QLineEdit(settings.get(path))
            edit.setMinimumWidth(220)
            edit.editingFinished.connect(lambda p=path, e=edit: self._hotkey_edited(p, e))
            self.key_edits[path] = edit
            keys.add(Row(label, edit))
        self.binder.settings.add_listener(lambda p: self.hotkeys_changed.emit() if p == "app.hotkeys_enabled" else None)
        self.key_status = QLabel("")
        self.key_status.setObjectName("Small")
        keys.add(self.key_status)
        lay.addWidget(keys)

        maint = Card("Help and maintenance")
        row = QHBoxLayout()
        for text, handler in (("Open documentation", self._open_docs),
                              ("Open config folder", lambda: open_path(config_dir())),
                              ("Open log folder", lambda: open_path(log_dir()))):
            b = QPushButton(text)
            b.clicked.connect(handler)
            row.addWidget(b)
        row.addStretch()
        reset = QPushButton("Reset ALL settings")
        reset.setObjectName("Warn")
        reset.clicked.connect(self._reset_all)
        row.addWidget(reset)
        maint.add_layout(row)
        about = QLabel(f"{APP_NAME} {__version__} · settings: {config_dir()}")
        about.setObjectName("Small")
        about.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        maint.add(about)
        lay.addWidget(maint)
        lay.addStretch()
        outer.addWidget(scroll_page(content))

    def _autostart_changed(self, on: bool) -> None:
        try:
            autostart.set_enabled(on)
            self.binder.set("app.autostart", on)
        except Exception as exc:
            QMessageBox.warning(self, "Start with Windows", f"Could not change the startup setting:\n{exc}")
            self.autostart.blockSignals(True)
            self.autostart.setChecked(autostart.is_enabled())
            self.autostart.blockSignals(False)

    def _hotkey_edited(self, path: str, edit: QLineEdit) -> None:
        text = edit.text().strip().lower()
        if text == self.settings.get(path):
            return
        try:
            from pynput import keyboard

            keyboard.HotKey.parse(text)
        except Exception as exc:
            self.key_status.setText(f"Invalid hotkey '{text}': {exc}")
            edit.setText(self.settings.get(path))
            return
        self.settings.set(path, text)
        self.key_status.setText(f"Saved {text}")
        self.hotkeys_changed.emit()

    def set_hotkey_error(self, error: str | None) -> None:
        if error:
            self.key_status.setText(f"Hotkeys unavailable: {error}")

    def _open_docs(self) -> None:
        if not open_docs():
            QMessageBox.information(self, "Documentation", f"Documentation not found at {docs_index()}")

    def _reset_all(self) -> None:
        if QMessageBox.question(self, "Reset settings", "Reset every setting and gesture to its default?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.settings.reset()
        self.binder.refresh_all()
        for path, edit in self.key_edits.items():
            edit.setText(self.settings.get(path))
        self.settings_reset.emit()
        self.hotkeys_changed.emit()

