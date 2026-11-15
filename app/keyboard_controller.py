"""Keyboard shortcuts used by window commands (via PyAutoGUI)."""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

# Only these fixed shortcuts can ever be sent - gestures never type arbitrary text or run commands.
SHORTCUTS = {
    "switch_app": ("alt", "tab") if sys.platform != "darwin" else ("command", "tab"),
    "snap_left": ("win", "left"),
    "snap_right": ("win", "right"),
    "maximize": ("win", "up"),
    "minimize": ("win", "down"),
}


class KeyboardController:
    def __init__(self) -> None:
        import pyautogui

        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0
        self._pg = pyautogui

    def hotkey(self, name: str) -> None:
        keys = SHORTCUTS.get(name)
        if keys is None:
            raise ValueError(f"Unknown shortcut {name!r}")
        log.debug("hotkey %s -> %s", name, "+".join(keys))
        self._pg.hotkey(*keys, interval=0.03)
