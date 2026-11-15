"""Main window: sidebar navigation, pages, system tray and tracking-thread lifecycle."""
from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox, QPushButton,
    QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from app import APP_NAME, __version__
from app.hotkeys import HotkeyManager
from app.logger import ActivityLog
from app.paths import asset_path
from app.settings_manager import SettingsManager
from app.tracking_worker import TrackingWorker
from ui import theme
from ui.activity_logs import ActivityLogsPage
from ui.camera_settings import CameraSettingsPage
from ui.cursor_settings import CursorSettingsPage
from ui.dashboard import DashboardPage
from ui.general_settings import GeneralSettingsPage, open_docs
from ui.gesture_settings import GestureSettingsPage

log = logging.getLogger(__name__)


class HotkeyBridge(QObject):
    """pynput callbacks run on their own thread; signals hop them onto the GUI thread."""

    pause = Signal()
    emergency = Signal()
    resume = Signal()


def status_icon(base: QIcon, color: str | None) -> QIcon:
    pix = base.pixmap(QSize(64, 64))
    if color is None:
        return QIcon(pix)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor("#0f1117"))
    p.setBrush(QColor(color))
    p.drawEllipse(38, 38, 24, 24)
    p.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsManager, activity: ActivityLog):
        super().__init__()
        self.settings = settings
        self.activity = activity
        self.worker: TrackingWorker | None = None
        self.paused = False
        self.stopped = False
        self._quitting = False
        self._auto_paused = False
        self.setWindowTitle(APP_NAME)
        self.app_icon = QIcon(str(asset_path("icon.png")))
        self.setWindowIcon(self.app_icon)
        self.resize(1280, 820)
        self.setMinimumSize(1020, 680)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- pages ---------------------------------------------------------------------
        self.dashboard = DashboardPage(settings)
        self.gestures = GestureSettingsPage(settings)
        self.camera = CameraSettingsPage(settings, lambda: self.worker is not None)
        self.cursor = CursorSettingsPage(settings)
        self.logs = ActivityLogsPage(activity)
        self.general = GeneralSettingsPage(settings)
        pages = [("Dashboard", self.dashboard), ("Gestures", self.gestures), ("Camera", self.camera),
                 ("Cursor", self.cursor), ("Activity logs", self.logs), ("Settings", self.general)]

        lay.addWidget(self._build_sidebar(pages))
        self.stack = QStackedWidget()
        for _, page in pages:
            self.stack.addWidget(page)
        lay.addWidget(self.stack, 1)

        # ---- dashboard wiring -------------------------------------------------------------
        self.dashboard.start_requested.connect(self.start_tracking)
        self.dashboard.stop_requested.connect(self.stop_tracking)
        self.dashboard.pause_toggled.connect(self.toggle_pause)
        self.dashboard.emergency_requested.connect(lambda: self.emergency_stop("Emergency button"))
        self.dashboard.resume_requested.connect(self.resume_control)
        self.general.hotkeys_changed.connect(self._register_hotkeys)
        self.general.hotkeys_changed.connect(self.dashboard.refresh_hotkeys)
        self.general.settings_reset.connect(self._settings_reset)
        settings.add_listener(self._settings_changed)

        self._build_tray()
        self.hotkeys = HotkeyManager()
        self.bridge = HotkeyBridge()
        self.bridge.pause.connect(self.toggle_pause)
        self.bridge.emergency.connect(lambda: self.emergency_stop("Emergency hotkey"))
        self.bridge.resume.connect(self.resume_control)
        self._register_hotkeys()
        self._update_controls()

    # ------------------------------------------------------------------ construction
    def _build_sidebar(self, pages) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        v = QVBoxLayout(side)
        v.setContentsMargins(16, 20, 16, 16)
        v.setSpacing(4)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(self.app_icon.pixmap(QSize(40, 40)))
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        n = QLabel("Gesture Mouse")
        n.setObjectName("AppName")
        t = QLabel("Touchless desktop control")
        t.setObjectName("AppTag")
        names.addWidget(n)
        names.addWidget(t)
        brand.addLayout(names, 1)
        v.addLayout(brand)
        v.addSpacing(22)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        for i, (name, _page) in enumerate(pages):
            b = QPushButton(name)
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav.addButton(b, i)
            v.addWidget(b)
        self.nav.button(0).setChecked(True)
        self.nav.idClicked.connect(lambda i: self.stack.setCurrentIndex(i))
        docs = QPushButton("Documentation  ↗")
        docs.setObjectName("Nav")
        docs.setCursor(Qt.CursorShape.PointingHandCursor)
        docs.clicked.connect(self._open_docs)
        v.addWidget(docs)
        v.addStretch()

        self.side_status = QLabel()
        self.side_status.setWordWrap(True)
        v.addWidget(self.side_status)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("Small")
        v.addWidget(ver)
        return side

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.app_icon, self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        self.act_open = QAction("Open dashboard", self, triggered=self.show_dashboard)
        self.act_track = QAction("Start tracking", self, triggered=self._tray_toggle_tracking)
        self.act_pause = QAction("Pause gestures", self, triggered=self.toggle_pause)
        self.act_stop = QAction("Emergency stop", self, triggered=lambda: self._tray_emergency())
        self.act_exit = QAction("Exit", self, triggered=self.quit)
        for a in (self.act_open, None, self.act_track, self.act_pause, self.act_stop, None, self.act_exit):
            menu.addSeparator() if a is None else menu.addAction(a)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self._tray_menu = menu
        self.icons = {
            "off": status_icon(self.app_icon, None),
            "active": status_icon(self.app_icon, theme.OK),
            "paused": status_icon(self.app_icon, theme.WARN),
            "stopped": status_icon(self.app_icon, theme.DANGER),
        }
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    # ------------------------------------------------------------------ tracking lifecycle
    def start_tracking(self) -> None:
        if self.worker is not None:
            return
        self.paused = False
        self.stopped = False
        self.dashboard.set_stopped(False)
        self.dashboard.set_paused(False)
        worker = TrackingWorker(self.settings, self.activity)
        worker.preview_enabled = self.isVisible() and bool(self.settings.get("app.show_preview"))
        worker.frame_ready.connect(self.dashboard.set_frame)
        worker.status.connect(self.dashboard.update_status)
        worker.camera_state.connect(self._camera_state)
        worker.notice.connect(self._notice)
        worker.fatal_error.connect(self._fatal)
        worker.finished.connect(self._worker_finished)
        self.worker = worker
        if not self.isVisible() and not self.settings.get("app.background_tracking"):
            worker.pause()
            self.paused = self._auto_paused = True
        worker.start()
        self.dashboard.set_tracking(False, starting=True)
        self._update_controls()

    def stop_tracking(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()
            self.dashboard.stop_btn.setEnabled(False)

    def _worker_finished(self) -> None:
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.paused = False
        self.stopped = False
        self.dashboard.set_tracking(False)
        self.dashboard.set_paused(False)
        self.dashboard.set_stopped(False)
        self._update_controls()

    def _camera_state(self, state: str, message: str) -> None:
        self.dashboard.set_camera(state, message)
        if state == "connected":
            self.dashboard.set_tracking(True)
        elif state == "error":
            self.dashboard.show_notice(f"Camera problem: {message}", theme.DANGER)
            if not self.isVisible():
                self.tray.showMessage(APP_NAME, f"Camera problem: {message}", QSystemTrayIcon.MessageIcon.Warning)
        self._update_controls()

    def _fatal(self, message: str) -> None:
        self.dashboard.show_notice(message, theme.DANGER)
        QMessageBox.critical(self, "Tracking error", message)

    def toggle_pause(self) -> None:
        if self.worker is None:
            return
        self._auto_paused = False
        self.paused = not self.paused
        (self.worker.pause if self.paused else self.worker.resume)()
        self.dashboard.set_paused(self.paused)
        self._update_controls()

    def emergency_stop(self, source: str) -> None:
        if self.worker is None or self.stopped:
            return
        self.worker.emergency_stop(source)
        self._set_stopped(True)

    def resume_control(self) -> None:
        if self.worker is None or not self.stopped:
            return
        self.worker.resume_from_stop()
        self._set_stopped(False)

    def _set_stopped(self, stopped: bool) -> None:
        self.stopped = stopped
        self.dashboard.set_stopped(stopped)
        if stopped and not self.isVisible():
            self.tray.showMessage(APP_NAME, "Emergency stop - gesture control is disabled. Open the dashboard "
                                            "or press the resume hotkey to continue.", QSystemTrayIcon.MessageIcon.Warning)
        self._update_controls()

    def _notice(self, kind: str, data: dict) -> None:
        if kind == "emergency_stop":
            self._set_stopped(True)
        elif kind == "resumed":
            self._set_stopped(False)
        elif kind == "close_armed":
            secs = data.get("seconds", 4)
            self.dashboard.show_notice(f"Close window armed - repeat the thumb + pinky hold within {secs:.0f} s to "
                                       f"confirm, or do nothing to cancel.")
            QTimer.singleShot(int(secs * 1000) + 300, self.dashboard.hide_notice)
        elif kind == "close_cancelled":
            self.dashboard.hide_notice()
        elif kind == "confirm_close":
            self._confirm_close(data["hwnd"], data.get("title", ""))

    def _confirm_close(self, hwnd: int, title: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Close window?")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Close <b>{title or 'this window'}</b>?")
        box.setInformativeText("This was requested by a gesture. Unsaved work may be lost if the application "
                               "does not ask to save.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        if box.exec() == QMessageBox.StandardButton.Yes and self.worker is not None:
            self.worker.close_window(hwnd)
        else:
            self.activity.add("Close confirmation", "Close cancelled in dialog")

    # ------------------------------------------------------------------ status display
    def _update_controls(self) -> None:
        running = self.worker is not None
        self.act_track.setText("Stop tracking" if running else "Start tracking")
        self.act_pause.setEnabled(running and not self.stopped)
        self.act_pause.setText("Resume gestures" if self.paused else "Pause gestures")
        self.act_stop.setEnabled(running)
        self.act_stop.setText("Resume control" if self.stopped else "Emergency stop")
        if not running:
            state, text, color = "off", "Tracking off", theme.MUTED
        elif self.stopped:
            state, text, color = "stopped", "Emergency stop", theme.DANGER
        elif self.paused:
            state, text, color = "paused", "Paused", theme.WARN
        else:
            state, text, color = "active", "Tracking active", theme.OK
        self.tray.setIcon(self.icons[state])
        self.tray.setToolTip(f"{APP_NAME} - {text}")
        self.side_status.setText(f"<span style='color:{color}; font-size:14pt'>●</span> "
                                 f"<span style='color:{theme.TEXT}; font-weight:600'>{text}</span>")

    # ------------------------------------------------------------------ settings & hotkeys
    def _settings_changed(self, path: str) -> None:
        if path.startswith("app.show_preview") and self.worker is not None:
            self.worker.preview_enabled = self.isVisible() and bool(self.settings.get("app.show_preview"))
            if not self.worker.preview_enabled:
                self.dashboard.preview.set_image(None)
                self.dashboard.preview.setText("Preview disabled in Settings")
        if path.startswith("gestures.emergency_stop"):
            self.dashboard.refresh_hotkeys()

    def _settings_reset(self) -> None:
        for page in (self.gestures, self.cursor, self.camera):
            page.binder.refresh_all()

    def _register_hotkeys(self) -> None:
        if not self.settings.get("app.hotkeys_enabled"):
            self.hotkeys.stop()
            return
        error = self.hotkeys.start({
            self.settings.get("app.hotkey_pause"): self.bridge.pause.emit,
            self.settings.get("app.hotkey_emergency"): self.bridge.emergency.emit,
            self.settings.get("app.hotkey_resume"): self.bridge.resume.emit,
        })
        self.general.set_hotkey_error(error)

    # ------------------------------------------------------------------ window / tray behaviour
    def _open_docs(self) -> None:
        if not open_docs():
            QMessageBox.information(self, "Documentation", "The documentation folder (docs/index.html) was not found.")

    def show_dashboard(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.stack.setCurrentIndex(0)
        self.nav.button(0).setChecked(True)

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_dashboard()

    def _tray_toggle_tracking(self) -> None:
        self.stop_tracking() if self.worker is not None else self.start_tracking()

    def _tray_emergency(self) -> None:
        self.resume_control() if self.stopped else self.emergency_stop("Tray menu")

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.worker is not None:
            self.worker.preview_enabled = bool(self.settings.get("app.show_preview"))
            if self._auto_paused:
                self._auto_paused = False
                self.paused = False
                self.worker.resume()
                self.dashboard.set_paused(False)
                self._update_controls()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        if self.worker is not None:
            self.worker.preview_enabled = False  # never render frames nobody can see
            if not self.settings.get("app.background_tracking") and not self.paused:
                self._auto_paused = True
                self.paused = True
                self.worker.pause()
                self.dashboard.set_paused(True)
                self._update_controls()

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.Type.WindowStateChange and self.worker is not None:
            self.worker.preview_enabled = not self.isMinimized() and bool(self.settings.get("app.show_preview"))
        super().changeEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._quitting and self.settings.get("app.minimize_to_tray") and self.tray.isVisible():
            event.ignore()
            self.hide()
            if not self.settings.get("app.tray_notice_shown"):
                self.tray.showMessage(APP_NAME, "Still running in the system tray. Right-click the tray icon to exit.",
                                      QSystemTrayIcon.MessageIcon.Information, 4000)
                self.settings.set("app.tray_notice_shown", True)
            return
        self._shutdown()
        event.accept()
        QApplication.instance().quit()

    def quit(self) -> None:
        self._quitting = True
        self.close()

    def _shutdown(self) -> None:
        self.hotkeys.stop()
        self.camera.shutdown()
        if self.worker is not None:
            self.worker.request_stop()
            if not self.worker.wait(4000):
                log.warning("Tracking thread did not stop in time")
        self.tray.hide()
        self.settings.save()

