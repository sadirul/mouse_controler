"""Start with Windows (HKCU Run key). Other platforms report the feature as unsupported."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from app import APP_ID
from app.paths import is_frozen, resource_root

log = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def supported() -> bool:
    return sys.platform == "win32"


def launch_command() -> str:
    if is_frozen():
        return f'"{sys.executable}" --minimized'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else exe
    return f'"{interpreter}" "{resource_root() / "main.py"}" --minimized'


def is_enabled() -> bool:
    if not supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_ID)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if not supported():
        raise RuntimeError("Start with the operating system is only supported on Windows")
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, launch_command())
            log.info("Autostart enabled: %s", launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_ID)
            except FileNotFoundError:
                pass
            log.info("Autostart disabled")
