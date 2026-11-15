"""OS-level mouse control.

On Windows a native ``SendInput`` backend is used: it addresses the whole virtual desktop (monitors
left of / above the primary have negative coordinates, which PyAutoGUI clamps away) and supports
high-resolution wheel deltas for smooth scrolling. On other platforms PyAutoGUI is used.

``MouseController`` is the only place in the application that presses mouse buttons, and it
tracks which buttons it is holding so they can always be released (stop, pause, exit, errors).
"""
from __future__ import annotations

import ctypes
import logging
import sys
from typing import Protocol

from app.cursor_controller import Rect

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"


class MouseBackend(Protocol):
    def move(self, x: int, y: int) -> None: ...
    def position(self) -> tuple[int, int]: ...
    def button(self, button: str, down: bool) -> None: ...
    def wheel(self, vertical: float, horizontal: float) -> None: ...  # in notches


# --------------------------------------------------------------------------------------
# Windows native backend
# --------------------------------------------------------------------------------------
if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    INPUT_MOUSE = 0
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_HWHEEL = 0x01000
    WHEEL_DELTA = 120

    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
    user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)

    _BUTTON_FLAGS = {
        ("left", True): MOUSEEVENTF_LEFTDOWN,
        ("left", False): MOUSEEVENTF_LEFTUP,
        ("right", True): MOUSEEVENTF_RIGHTDOWN,
        ("right", False): MOUSEEVENTF_RIGHTUP,
        ("middle", True): MOUSEEVENTF_MIDDLEDOWN,
        ("middle", False): MOUSEEVENTF_MIDDLEUP,
    }

    def _send_mouse(flags: int, data: int = 0) -> None:
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(0, 0, ctypes.c_uint32(data).value, flags, 0, 0)
        if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
            raise OSError(f"SendInput failed (error {ctypes.get_last_error()}). "
                          "The target window may be elevated (run as administrator).")

    class WindowsMouseBackend:
        def move(self, x: int, y: int) -> None:
            if not user32.SetCursorPos(int(x), int(y)):
                raise OSError(f"SetCursorPos failed (error {ctypes.get_last_error()})")

        def position(self) -> tuple[int, int]:
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            return pt.x, pt.y

        def button(self, button: str, down: bool) -> None:
            _send_mouse(_BUTTON_FLAGS[(button, down)])

        def wheel(self, vertical: float, horizontal: float) -> None:
            if vertical:
                _send_mouse(MOUSEEVENTF_WHEEL, int(round(vertical * WHEEL_DELTA)))
            if horizontal:
                _send_mouse(MOUSEEVENTF_HWHEEL, int(round(horizontal * WHEEL_DELTA)))


class PyAutoGuiMouseBackend:
    """Cross-platform backend. Wheel deltas are accumulated into whole notches."""

    def __init__(self) -> None:
        import pyautogui

        pyautogui.FAILSAFE = False  # corners are valid targets; we have our own emergency stop
        pyautogui.PAUSE = 0
        self._pg = pyautogui
        self._acc_v = 0.0
        self._acc_h = 0.0

    def move(self, x: int, y: int) -> None:
        self._pg.moveTo(x, y, _pause=False)

    def position(self) -> tuple[int, int]:
        p = self._pg.position()
        return int(p[0]), int(p[1])

    def button(self, button: str, down: bool) -> None:
        if down:
            self._pg.mouseDown(button=button, _pause=False)
        else:
            self._pg.mouseUp(button=button, _pause=False)

    def wheel(self, vertical: float, horizontal: float) -> None:
        self._acc_v += vertical
        self._acc_h += horizontal
        v, h = int(self._acc_v), int(self._acc_h)
        if v:
            self._acc_v -= v
            self._pg.scroll(v, _pause=False)
        if h:
            self._acc_h -= h
            try:
                self._pg.hscroll(h, _pause=False)
            except Exception:  # not supported on every platform
                log.debug("horizontal scroll unsupported on this platform")


def default_backend() -> MouseBackend:
    if IS_WINDOWS:
        return WindowsMouseBackend()
    return PyAutoGuiMouseBackend()


# --------------------------------------------------------------------------------------
# Screen geometry
# --------------------------------------------------------------------------------------
def list_monitors() -> list[Rect]:
    """Physical-pixel rectangles of all monitors, primary first."""
    if IS_WINDOWS:
        monitors: list[tuple[bool, Rect]] = []

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                                             ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

        def _cb(hmon, _hdc, _rect, _lp):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                r = info.rcMonitor
                monitors.append((bool(info.dwFlags & 1), Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)))
            return 1

        user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)
        if monitors:
            monitors.sort(key=lambda m: (not m[0], m[1].left, m[1].top))
            return [m[1] for m in monitors]
    try:
        import pyautogui

        w, h = pyautogui.size()
        return [Rect(0, 0, int(w), int(h))]
    except Exception:  # pragma: no cover
        return [Rect(0, 0, 1920, 1080)]


def virtual_screen() -> Rect:
    monitors = list_monitors()
    left = min(m.left for m in monitors)
    top = min(m.top for m in monitors)
    right = max(m.left + m.width for m in monitors)
    bottom = max(m.top + m.height for m in monitors)
    return Rect(left, top, right - left, bottom - top)


def target_screen(monitor_setting: str) -> Rect:
    """Resolve the ``cursor.monitor`` setting (all | primary | <index>) to a rectangle."""
    monitors = list_monitors()
    if monitor_setting == "all":
        return virtual_screen()
    if monitor_setting == "primary":
        return monitors[0]
    try:
        return monitors[int(monitor_setting)]
    except (ValueError, IndexError):
        return monitors[0]


# --------------------------------------------------------------------------------------
# Controller
# --------------------------------------------------------------------------------------
class MouseController:
    def __init__(self, backend: MouseBackend | None = None):
        self.backend = backend or default_backend()
        self._held: set[str] = set()

    @property
    def held_buttons(self) -> set[str]:
        return set(self._held)

    def move(self, x: int, y: int) -> None:
        self.backend.move(x, y)

    def position(self) -> tuple[int, int]:
        return self.backend.position()

    def click(self, button: str = "left", count: int = 1) -> None:
        if button in self._held:  # never click a button we are holding down
            self.up(button)
        for _ in range(count):
            self.backend.button(button, True)
            self.backend.button(button, False)

    def double_click(self) -> None:
        self.click("left", 2)

    def down(self, button: str = "left") -> None:
        if button in self._held:
            return
        self.backend.button(button, True)
        self._held.add(button)

    def up(self, button: str = "left") -> None:
        if button not in self._held:
            return
        self._held.discard(button)
        self.backend.button(button, False)

    def scroll(self, vertical: float = 0.0, horizontal: float = 0.0) -> None:
        self.backend.wheel(vertical, horizontal)

    def release_all(self) -> None:
        for button in list(self._held):
            try:
                self.up(button)
            except Exception:  # pragma: no cover - best effort during shutdown
                log.exception("Failed to release %s button", button)
                self._held.discard(button)
