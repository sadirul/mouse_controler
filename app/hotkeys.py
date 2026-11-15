"""System-wide safety hotkeys (pynput).

They work even when the application window is hidden or the gesture cursor is somewhere awkward:
* pause / resume gesture control
* emergency stop
* resume after an emergency stop
"""
from __future__ import annotations

import logging
from typing import Callable

log = logging.getLogger(__name__)


class HotkeyManager:
    def __init__(self) -> None:
        self._listener = None

    def start(self, bindings: dict[str, Callable[[], None]]) -> str | None:
        """Register ``{"<ctrl>+<alt>+p": callback, ...}``. Returns an error message on failure."""
        self.stop()
        bindings = {k: v for k, v in bindings.items() if k}
        if not bindings:
            return None
        try:
            from pynput import keyboard

            self._listener = keyboard.GlobalHotKeys(bindings)
            self._listener.daemon = True
            self._listener.start()
            log.info("Global hotkeys registered: %s", ", ".join(bindings))
            return None
        except Exception as exc:
            log.warning("Global hotkeys unavailable: %s", exc)
            self._listener = None
            return str(exc)

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # pragma: no cover
                pass
            self._listener = None


def pretty(hotkey: str) -> str:
    return "+".join(part.strip("<>").capitalize() for part in hotkey.split("+")) if hotkey else "-"
