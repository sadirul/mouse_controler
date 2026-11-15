"""Resolve resource and user-data locations for source and frozen (PyInstaller) runs."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from app import APP_ID


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Directory that contains bundled read-only resources (models, assets, default config)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def user_data_dir() -> Path:
    """Writable directory for settings and logs.

    Running from source keeps everything inside the project (config/, logs/) so it is easy to
    inspect. The packaged executable stores data in %APPDATA%/HandGestureMouse (or the XDG/macOS
    equivalent) because the install directory may be read-only.
    """
    override = os.environ.get("HGM_DATA_DIR")
    if override:
        path = Path(override)
    elif is_frozen():
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        path = base / APP_ID
    else:
        path = resource_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    path = user_data_dir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_path() -> Path:
    return resource_path("models", "hand_landmarker.task")


def asset_path(*parts: str) -> Path:
    return resource_path("ui", "assets", *parts)


def docs_index() -> Path:
    return resource_path("docs", "index.html")
