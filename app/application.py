"""Application bootstrap: logging, single instance, Qt app, main window."""
from __future__ import annotations

import argparse
import logging
import sys

from app import APP_ID, APP_NAME, __version__

log = logging.getLogger(__name__)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="HandGestureMouse", description=APP_NAME)
    parser.add_argument("--minimized", action="store_true", help="start hidden in the system tray")
    parser.add_argument("--start-tracking", action="store_true", help="start hand tracking immediately")
    parser.add_argument("--self-test", action="store_true", help="run diagnostics (camera, model, gesture engine) and exit")
    parser.add_argument("--quiet", action="store_true", help="with --self-test: no dialog, only the report file")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    import os

    if sys.stdout is None:  # windowed executable: give argparse/print somewhere harmless to write
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.self_test:
        from app.selftest import main as self_test

        return self_test(show_dialog=not args.quiet)

    from app.logger import ActivityLog, setup_logging

    setup_logging()
    log.info("%s %s starting (Python %s)", APP_NAME, __version__, sys.version.split()[0])

    if sys.platform == "win32":
        try:  # separate taskbar identity (correct icon) for the Python-hosted app
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_ID}.{__version__}")
        except Exception:
            pass

    from PySide6.QtCore import QDir, QLockFile, Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    # Qt 6 is per-monitor DPI aware, so Win32 cursor coordinates are physical pixels everywhere.
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    app.setQuitOnLastWindowClosed(False)  # keep running in the tray

    lock = QLockFile(QDir.tempPath() + f"/{APP_ID}.lock")
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, f"{APP_NAME} is already running - look for its icon in the system tray.")
        return 0

    from ui import theme
    from ui.main_window import MainWindow
    from app.settings_manager import SettingsManager

    app.setStyle("Fusion")
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.STYLE)

    settings = SettingsManager()
    activity = ActivityLog()
    window = MainWindow(settings, activity)
    app.setWindowIcon(window.app_icon)

    start_hidden = args.minimized or settings.get("app.start_minimized")
    if start_hidden and window.tray.isVisible():
        log.info("Started minimised to tray")
    else:
        window.show()
    if args.start_tracking or settings.get("app.auto_start_tracking"):
        window.start_tracking()

    def excepthook(exc_type, exc, tb):  # keep the app alive and the mouse released on GUI errors
        log.error("Unhandled exception", exc_info=(exc_type, exc, tb))
        try:
            QMessageBox.critical(window, APP_NAME, f"Unexpected error:\n{exc}\n\nDetails are in the log file.")
        except Exception:
            pass

    sys.excepthook = excepthook
    code = app.exec()
    lock.unlock()
    log.info("Exited with code %s", code)
    return code
