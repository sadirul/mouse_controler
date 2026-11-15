"""Application logging and the user-facing activity log."""
from __future__ import annotations

import logging
import sys
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Callable

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging to a rotating file and stderr (when a console exists)."""
    global _configured
    if _configured:
        return
    from app.paths import log_dir

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    try:
        fh = RotatingFileHandler(log_dir() / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    for noisy in ("PIL", "matplotlib", "absl"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


@dataclass
class ActivityEntry:
    gesture: str
    action: str
    success: bool = True
    error: str = ""
    time: datetime = field(default_factory=datetime.now)

    @property
    def time_text(self) -> str:
        return self.time.strftime("%H:%M:%S.") + f"{self.time.microsecond // 1000:03d}"


class ActivityLog:
    """Thread-safe ring buffer of gesture -> action results shown in the Activity Logs page."""

    def __init__(self, maxlen: int = 2000):
        self._entries: deque[ActivityEntry] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._listeners: list[Callable[[ActivityEntry], None]] = []
        self._log = logging.getLogger("activity")

    def add(self, gesture: str, action: str, success: bool = True, error: str = "") -> ActivityEntry:
        entry = ActivityEntry(gesture, action, success, error)
        with self._lock:
            self._entries.append(entry)
        if success:
            self._log.info("%s -> %s", gesture, action)
        else:
            self._log.warning("%s -> %s FAILED: %s", gesture, action, error)
        for callback in list(self._listeners):
            try:
                callback(entry)
            except Exception:  # pragma: no cover
                logging.getLogger(__name__).exception("activity listener failed")
        return entry

    def entries(self) -> list[ActivityEntry]:
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def add_listener(self, callback: Callable[[ActivityEntry], None]) -> None:
        self._listeners.append(callback)
