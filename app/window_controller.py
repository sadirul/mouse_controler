"""Window management: grab-and-move, minimise / maximise / restore / close, snapping, app switching.

Uses PyGetWindow for window objects and a few Win32 calls (via ctypes) for the things PyGetWindow
does not expose: window class names (to protect the desktop and taskbar), monitor work areas, and
flicker-free ``SetWindowPos`` moves. On macOS / Linux window management is reported as unsupported
instead of pretending to work.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
from dataclasses import dataclass

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

# Shell windows that must never be moved, minimised or closed by a gesture.
PROTECTED_CLASSES = {
    "Progman",  # desktop (closing it opens the shutdown dialog)
    "WorkerW",
    "Shell_TrayWnd",  # taskbar
    "Shell_SecondaryTrayWnd",
    "NotifyIconOverflowWindow",
    "Windows.UI.Core.CoreWindow",  # start menu / search / action center
    "XamlExplorerHostIslandWindow",
    "TaskListThumbnailWnd",
    "MultitaskingViewFrame",
    "ForegroundStaging",
}


class WindowError(RuntimeError):
    pass


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    left: int
    top: int
    width: int
    height: int
    maximized: bool
    pid: int


if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.WindowFromPoint.argtypes = (wintypes.POINT,)
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT)
    user32.IsZoomed.argtypes = (wintypes.HWND,)
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindow.argtypes = (wintypes.HWND,)
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)

    GA_ROOT = 2
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SW_RESTORE = 9
    MONITOR_DEFAULTTONEAREST = 2

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class WindowController:
    def __init__(self) -> None:
        self.supported = IS_WINDOWS
        self._gw = None
        if IS_WINDOWS:
            try:
                import pygetwindow

                self._gw = pygetwindow
            except Exception as exc:  # pragma: no cover
                log.warning("PyGetWindow unavailable: %s", exc)
        self._grab: WindowInfo | None = None
        self._grab_origin: tuple[int, int] | None = None
        self.own_pid = os.getpid()

    # ------------------------------------------------------------------ queries
    def _require(self) -> None:
        if not self.supported:
            raise WindowError("Window management is only implemented for Windows in this version")

    def info(self, hwnd: int) -> WindowInfo:
        self._require()
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        cls = buf.value
        title_buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title_buf, 512)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return WindowInfo(
            hwnd=int(hwnd), title=title_buf.value, class_name=cls,
            left=rect.left, top=rect.top, width=rect.right - rect.left, height=rect.bottom - rect.top,
            maximized=bool(user32.IsZoomed(hwnd)), pid=pid.value,
        )

    def target(self, mode: str = "active") -> WindowInfo:
        """The window a command should act on: the foreground window or the one under the cursor."""
        self._require()
        if mode == "under_cursor":
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            hwnd = user32.WindowFromPoint(pt)
            hwnd = user32.GetAncestor(hwnd, GA_ROOT) if hwnd else None
        else:
            hwnd = user32.GetForegroundWindow()
        if not hwnd or not user32.IsWindow(hwnd):
            raise WindowError("No window found")
        info = self.info(hwnd)
        if info.class_name in PROTECTED_CLASSES or not user32.IsWindowVisible(hwnd):
            raise WindowError(f"'{info.title or info.class_name}' is a protected system window")
        return info

    def _gw_window(self, info: WindowInfo):
        if self._gw is None:
            raise WindowError("PyGetWindow is not available")
        return self._gw.Win32Window(info.hwnd)

    def work_area(self, hwnd: int) -> tuple[int, int, int, int]:
        mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(mon, ctypes.byref(mi))
        r = mi.rcWork
        return r.left, r.top, r.right - r.left, r.bottom - r.top

    # ------------------------------------------------------------------ grab and move
    def begin_move(self, mode: str = "active") -> WindowInfo:
        info = self.target(mode)
        if info.maximized or user32.IsIconic(info.hwnd):
            # Like dragging a maximised window's title bar: restore it first.
            user32.ShowWindow(info.hwnd, SW_RESTORE)
            info = self.info(info.hwnd)
        self._grab = info
        self._grab_origin = (info.left, info.top)
        return info

    def move_by(self, dx: int, dy: int) -> None:
        if self._grab is None or self._grab_origin is None:
            return
        x = self._grab_origin[0] + int(dx)
        y = self._grab_origin[1] + int(dy)
        ok = user32.SetWindowPos(self._grab.hwnd, None, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        if not ok:
            err = ctypes.get_last_error()
            self._grab = None
            raise WindowError(f"Window could not be moved (error {err}); it may belong to an elevated app")

    def end_move(self) -> WindowInfo | None:
        info, self._grab, self._grab_origin = self._grab, None, None
        return info

    @property
    def grabbing(self) -> bool:
        return self._grab is not None

    def title_bar_point(self, info: WindowInfo) -> tuple[int, int]:
        """A point on the title bar used by the alternative "title bar drag" move mode."""
        caption = user32.GetSystemMetrics(4) or 23  # SM_CYCAPTION
        frame = user32.GetSystemMetrics(33) or 4  # SM_CYSIZEFRAME
        return info.left + info.width // 2, info.top + frame + caption // 2

    # ------------------------------------------------------------------ commands
    def command(self, action: str, mode: str = "active") -> str:
        """Execute a window command and return a human readable description."""
        if action in ("next_app", "previous_app"):
            from app import app_switcher

            try:
                return app_switcher.switch("next" if action == "next_app" else "previous")
            except app_switcher.AppSwitchError as exc:
                raise WindowError(str(exc)) from exc
        if action == "lock_screen":
            if not IS_WINDOWS:
                raise WindowError("Locking the computer is only supported on Windows")
            if not user32.LockWorkStation():
                raise WindowError("Windows refused to lock the computer")
            return "Locked Windows (Win+L)"
        self._require()
        if action == "switch_app":
            from app.keyboard_controller import KeyboardController

            KeyboardController().hotkey("switch_app")
            return "Switched application (Alt+Tab)"
        info = self.target(mode)
        win = self._gw_window(info)
        name = info.title or info.class_name
        if action == "minimize":
            win.minimize()
            return f"Minimized '{name}'"
        if action == "maximize":
            win.maximize()
            return f"Maximized '{name}'"
        if action == "restore":
            win.restore()
            return f"Restored '{name}'"
        if action == "restore_or_minimize":
            if info.maximized:
                win.restore()
                return f"Restored '{name}'"
            win.minimize()
            return f"Minimized '{name}'"
        if action == "maximize_toggle":
            if info.maximized:
                win.restore()
                return f"Restored '{name}'"
            win.maximize()
            return f"Maximized '{name}'"
        if action == "close":
            if info.pid == self.own_pid:
                raise WindowError("Refusing to close Hand Gesture Mouse itself with a gesture")
            win.close()  # WM_CLOSE: the app can still ask to save unsaved work
            return f"Closed '{name}'"
        if action in ("snap_left", "snap_right", "move_top"):
            if info.maximized:
                win.restore()
                info = self.info(info.hwnd)
            wx, wy, ww, wh = self.work_area(info.hwnd)
            if action == "snap_left":
                win.moveTo(wx, wy)
                win.resizeTo(ww // 2, wh)
                return f"Snapped '{name}' left"
            if action == "snap_right":
                win.moveTo(wx + ww // 2, wy)
                win.resizeTo(ww - ww // 2, wh)
                return f"Snapped '{name}' right"
            win.moveTo(info.left, wy)
            return f"Moved '{name}' to the top"
        raise WindowError(f"Unknown window action {action!r}")

    def close_window(self, hwnd: int) -> str:
        """Close a specific window (used after the confirmation dialog)."""
        self._require()
        if not user32.IsWindow(hwnd):
            raise WindowError("The window no longer exists")
        info = self.info(hwnd)
        if info.class_name in PROTECTED_CLASSES:
            raise WindowError("Protected system window")
        if info.pid == self.own_pid:
            raise WindowError("Refusing to close Hand Gesture Mouse itself with a gesture")
        self._gw_window(info).close()
        return f"Closed '{info.title or info.class_name}'"

    def activate(self, hwnd: int) -> None:
        if IS_WINDOWS:
            user32.SetForegroundWindow(hwnd)
