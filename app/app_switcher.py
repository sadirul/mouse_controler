"""Flip between open applications like a carousel (open-hand slide gesture).

``next``: the current app goes to the back of the window stack and the app behind it comes to the
front. ``previous`` undoes that: the app at the back comes to the front. So next, next, previous,
previous returns to where you started - unlike Alt+Tab, which only toggles between two apps.

The ordering logic (:func:`plan`) is pure and unit-tested; the Win32 part enumerates the windows
that Alt+Tab would show and activates one.
"""
from __future__ import annotations

import ctypes
import os
import sys

IS_WINDOWS = sys.platform == "win32"


class AppSwitchError(RuntimeError):
    pass


def plan(stack: list[int], foreground: int | None, direction: str) -> tuple[int | None, int | None]:
    """Return (window to activate, window to send to the back) for a flip.

    ``stack`` lists the switchable windows front to back.
    """
    if len(stack) < 2:
        return None, None
    current = foreground if foreground in stack else stack[0]
    if direction == "next":
        others = [h for h in stack if h != current]
        return others[0], current
    if direction == "previous":
        target = stack[-1] if stack[-1] != current else stack[-2]
        return target, None
    raise ValueError(f"Unknown direction {direction!r}")


if IS_WINDOWS:
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi")
    _kernel32 = ctypes.WinDLL("kernel32")
    _user32.GetTopWindow.argtypes = (wintypes.HWND,)
    _user32.GetTopWindow.restype = wintypes.HWND
    _user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
    _user32.GetWindow.restype = wintypes.HWND
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
    _user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    _user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    _user32.IsIconic.argtypes = (wintypes.HWND,)
    _user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    _user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    _user32.BringWindowToTop.argtypes = (wintypes.HWND,)
    _user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wintypes.UINT)
    _user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    _user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    _dwmapi.DwmGetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)

    GW_HWNDNEXT = 2
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_NOACTIVATE = 0x08000000
    DWMWA_CLOAKED = 14
    SW_RESTORE = 9
    HWND_BOTTOM = 1
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
    MOUSEEVENTF_MOVE = 0x0001


def _skip_classes() -> set[str]:
    from app.window_controller import PROTECTED_CLASSES

    return set(PROTECTED_CLASSES) | {"Windows.UI.Core.CoreWindow", "ApplicationFrameWindow_Hidden"}


def _switchable(hwnd, own_pid: int, skip: set[str]) -> bool:
    if not _user32.IsWindowVisible(hwnd) or _user32.GetWindow(hwnd, GW_OWNER):
        return False
    ex = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TOOLWINDOW or ex & WS_EX_NOACTIVATE:
        return False
    if _user32.GetWindowTextLengthW(hwnd) == 0:
        return False
    cloaked = wintypes.DWORD()
    if _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 and cloaked.value:
        return False  # suspended Store apps / windows on other virtual desktops
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    if buf.value in skip:
        return False
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value != own_pid


def window_stack() -> list[int]:
    """Switchable top-level windows, front to back (what Alt+Tab would list)."""
    if not IS_WINDOWS:
        raise AppSwitchError("App switching is only supported on Windows")
    own_pid, skip = os.getpid(), _skip_classes()
    stack: list[int] = []
    hwnd = _user32.GetTopWindow(None)
    while hwnd:
        if _switchable(hwnd, own_pid, skip):
            stack.append(int(hwnd))
        hwnd = _user32.GetWindow(hwnd, GW_HWNDNEXT)
    return stack


def _title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def _activate(hwnd: int) -> None:
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, SW_RESTORE)
    # Windows only lets the process that produced the last input change the foreground window; a
    # zero-length mouse move makes that us. Attaching to the foreground thread is the fallback.
    _user32.mouse_event(MOUSEEVENTF_MOVE, 0, 0, 0, 0)
    if _user32.SetForegroundWindow(hwnd) and _user32.GetForegroundWindow() == hwnd:
        return
    fg = _user32.GetForegroundWindow()
    fg_thread = _user32.GetWindowThreadProcessId(fg, None) if fg else 0
    me = _kernel32.GetCurrentThreadId()
    if fg_thread and fg_thread != me:
        _user32.AttachThreadInput(me, fg_thread, True)
        try:
            _user32.BringWindowToTop(hwnd)
            _user32.SetForegroundWindow(hwnd)
        finally:
            _user32.AttachThreadInput(me, fg_thread, False)


def switch(direction: str) -> str:
    """Flip to the next or previous app. Returns a description for the activity log."""
    stack = window_stack()
    fg = _user32.GetForegroundWindow()
    target, to_back = plan(stack, int(fg) if fg else None, direction)
    if target is None:
        return "No other app to switch to"
    if to_back is not None:
        _user32.SetWindowPos(to_back, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
    _activate(target)
    label = "Next app" if direction == "next" else "Previous app"
    return f"{label}: '{_title(target)}'"
