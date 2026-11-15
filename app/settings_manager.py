"""Persistent JSON configuration.

Two files are used:

* ``settings.json`` - camera, tracking, cursor and application preferences.
* ``gestures.json`` - per-gesture enable flags, thresholds, durations, cooldowns and the
  window-command mappings.

Values are always merged on top of the built-in defaults below, so a partially edited or
older configuration file still loads, and type mismatches fall back to the default value.
Keys are addressed with dotted paths, e.g. ``cursor.smoothing`` or ``gestures.click.cooldown_ms``.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------------------

DEFAULT_SETTINGS: dict[str, Any] = {
    "camera": {
        "device": 0,
        "width": 640,
        "height": 480,
        "fps": 30,
        "mirror": True,
    },
    "tracking": {
        "max_fps": 30,
        "preferred_hand": "any",  # right | left | any
        "min_detection_confidence": 0.6,
        "min_presence_confidence": 0.5,
        "min_tracking_confidence": 0.5,
        "min_hand_score": 0.6,  # handedness confidence required to act on a hand
    },
    "cursor": {
        "mode": "absolute",  # absolute | relative
        "speed": 1.0,  # absolute: shrinks the active camera region; relative: gain
        "smoothing": 0.55,  # 0 = raw, 1 = very smooth (One Euro min cutoff)
        "responsiveness": 0.5,  # One Euro beta - lowers lag on fast motion
        "acceleration": 0.6,  # relative mode only
        "dead_zone_px": 2,
        "pinch_damping": 0.35,  # cursor gain while the thumb approaches the index finger
        "region": {"left": 0.15, "right": 0.85, "top": 0.12, "bottom": 0.72},
        "monitor": "all",  # all | primary | <index as string>
    },
    "app": {
        "minimize_to_tray": True,
        "background_tracking": True,
        "start_minimized": False,
        "autostart": False,
        "auto_start_tracking": False,
        "show_preview": True,
        "hotkeys_enabled": True,
        "hotkey_pause": "<ctrl>+<alt>+p",
        "hotkey_emergency": "<ctrl>+<alt>+x",
        "hotkey_resume": "<ctrl>+<alt>+r",
        "tray_notice_shown": False,
    },
}

DEFAULT_GESTURES: dict[str, Any] = {
    "gestures": {
        "move": {"enabled": True, "min_ms": 40},
        "click": {
            "enabled": True,
            "min_ms": 40,
            "cooldown_ms": 120,
            "pinch_threshold": 0.28,
            "release_threshold": 0.38,
        },
        "double_click": {"enabled": True, "interval_ms": 350},
        "right_click": {
            "enabled": True,
            "min_ms": 80,
            "cooldown_ms": 400,
            "pinch_threshold": 0.28,
        },
        "long_press": {"enabled": True, "duration_ms": 800, "mode": "hold"},  # hold | right_click
        "drag": {"enabled": True, "on_move": True, "move_threshold": 0.025},
        "scroll": {
            "enabled": True,
            "min_ms": 120,
            "mode": "touchpad",  # touchpad | joystick
            "require_together": True,
            "together_threshold": 0.45,
            "axis_lock_threshold": 0.015,
            "dead_zone": 0.003,
        },
        "scroll_vertical": {"enabled": True, "speed": 30.0},
        "scroll_horizontal": {"enabled": True, "speed": 30.0},
        "window_move": {
            "enabled": True,
            "min_ms": 250,
            "pose": "index_middle_ring",  # index_middle_ring | thumb_index_middle
            "mode": "direct",  # direct | titlebar
            "target": "active",  # active | under_cursor
            "gain": 1.0,
        },
        "window_swipe": {
            "enabled": True,
            "min_ms": 80,
            "distance": 0.9,  # in hand-sizes
            "window_ms": 650,
            "cooldown_ms": 900,
        },
        "horns": {"enabled": True, "hold_ms": 600, "cooldown_ms": 1200},
        "thumb_pinky": {
            "enabled": True,
            "hold_ms": 700,
            "cooldown_ms": 300,
            "pinch_threshold": 0.32,
        },
        "close_confirm": {"mode": "gesture", "window_ms": 4000},  # gesture | dialog
        "emergency_stop": {"enabled": True, "hold_ms": 1500, "require_palm_facing": False},
        "resume": {"enabled": True, "pose": "fist", "hold_ms": 2000},  # pose: fist | horns
        # Two-hand camera frame (an L with each hand). folder "" = Pictures/Screenshots
        "screenshot": {"enabled": True, "hold_ms": 800, "cooldown_ms": 2000, "folder": ""},
        # Open hand slid sideways by `distance` hand sizes within `window_ms`. The opposite direction
        # is ignored for `return_ms` afterwards (the hand swinging back).
        # Two index fingers crossed like an X, held for hold_ms
        "cross_x": {"enabled": True, "hold_ms": 500, "cooldown_ms": 3000},
        "palm_slide": {"enabled": True, "distance": 1.2, "window_ms": 400, "cooldown_ms": 500, "return_ms": 900},
        "mappings": {
            "four_swipe_up": "maximize",
            "four_swipe_down": "restore_or_minimize",
            "four_swipe_left": "snap_left",
            "four_swipe_right": "snap_right",
            "horns_hold": "switch_app",
            "thumb_pinky_hold": "close",
            "palm_slide_left": "previous_app",
            "palm_slide_right": "next_app",
            "cross_x": "lock_screen",
        },
    }
}

WINDOW_ACTIONS = [
    "none",
    "minimize",
    "maximize",
    "restore",
    "restore_or_minimize",
    "maximize_toggle",
    "close",
    "switch_app",
    "snap_left",
    "snap_right",
    "move_top",
    "empty_recycle_bin",  # always confirmed in a dialog
    "lock_screen",  # same as Win+L
    "next_app",  # carousel: current app to the back, the one behind it to the front
    "previous_app",
]

WINDOW_TRIGGERS = [
    "four_swipe_up",
    "four_swipe_down",
    "four_swipe_left",
    "four_swipe_right",
    "horns_hold",
    "thumb_pinky_hold",
    "palm_slide_left",
    "palm_slide_right",
    "cross_x",
]

# Values that must stay inside a range regardless of what the JSON says.
_RANGES: dict[str, tuple[float, float]] = {
    "camera.width": (160, 3840),
    "camera.height": (120, 2160),
    "camera.fps": (5, 120),
    "tracking.max_fps": (5, 120),
    "tracking.min_detection_confidence": (0.1, 0.99),
    "tracking.min_presence_confidence": (0.1, 0.99),
    "tracking.min_tracking_confidence": (0.1, 0.99),
    "tracking.min_hand_score": (0.0, 0.99),
    "cursor.speed": (0.3, 4.0),
    "cursor.smoothing": (0.0, 1.0),
    "cursor.responsiveness": (0.0, 1.0),
    "cursor.acceleration": (0.0, 3.0),
    "cursor.dead_zone_px": (0, 50),
    "cursor.pinch_damping": (0.0, 1.0),
    "gestures.click.pinch_threshold": (0.08, 0.8),
    "gestures.click.release_threshold": (0.1, 1.0),
    "gestures.right_click.pinch_threshold": (0.08, 0.8),
    "gestures.thumb_pinky.pinch_threshold": (0.08, 0.8),
    "gestures.double_click.interval_ms": (100, 1000),
    "gestures.long_press.duration_ms": (200, 5000),
    "gestures.emergency_stop.hold_ms": (500, 5000),
    "gestures.resume.hold_ms": (500, 5000),
    "gestures.screenshot.hold_ms": (200, 5000),
    "gestures.screenshot.cooldown_ms": (0, 10000),
    "gestures.palm_slide.distance": (0.5, 4.0),
    "gestures.cross_x.hold_ms": (100, 3000),
    "gestures.cross_x.cooldown_ms": (0, 10000),
    "gestures.palm_slide.window_ms": (150, 1000),
    "gestures.palm_slide.cooldown_ms": (0, 5000),
    "gestures.palm_slide.return_ms": (0, 3000),
}

FILES = {"settings": "settings.json", "gestures": "gestures.json"}


def _merge(defaults: Any, loaded: Any) -> Any:
    """Deep-merge ``loaded`` onto ``defaults`` keeping default types."""
    if isinstance(defaults, dict):
        result = copy.deepcopy(defaults)
        if isinstance(loaded, dict):
            for key, value in loaded.items():
                if key in defaults:  # unknown keys are dropped
                    result[key] = _merge(defaults[key], value)
        return result
    if loaded is None:
        return copy.deepcopy(defaults)
    if isinstance(defaults, bool):
        return loaded if isinstance(loaded, bool) else defaults
    if isinstance(defaults, (int, float)):
        if isinstance(loaded, bool) or not isinstance(loaded, (int, float)):
            return defaults
        return float(loaded) if isinstance(defaults, float) else int(round(loaded))
    if isinstance(defaults, str):
        return loaded if isinstance(loaded, str) else defaults
    return loaded


def _clamp_ranges(root: dict[str, Any]) -> None:
    for path, (lo, hi) in _RANGES.items():
        parts = path.split(".")
        node = root
        for part in parts[:-1]:
            node = node.get(part, {}) if isinstance(node, dict) else {}
        leaf = parts[-1]
        if isinstance(node, dict) and leaf in node and isinstance(node[leaf], (int, float)):
            value = min(max(node[leaf], lo), hi)
            node[leaf] = type(node[leaf])(value)


def _validate_mappings(root: dict[str, Any]) -> None:
    mappings = root.get("gestures", {}).get("mappings", {})
    for trigger in list(mappings.keys()):
        if trigger not in WINDOW_TRIGGERS:
            mappings.pop(trigger)
        elif mappings[trigger] not in WINDOW_ACTIONS:
            mappings[trigger] = DEFAULT_GESTURES["gestures"]["mappings"].get(trigger, "none")


class SettingsManager:
    """Thread-safe settings store backed by two JSON files."""

    def __init__(self, directory: str | os.PathLike | None = None):
        if directory is None:
            from app.paths import config_dir, is_frozen, resource_path

            directory = config_dir()
            if is_frozen():  # first run of the packaged app: start from the bundled defaults
                for name in FILES.values():
                    bundled, target = resource_path("config", name), Path(directory) / name
                    if bundled.exists() and not target.exists():
                        try:
                            shutil.copyfile(bundled, target)
                        except OSError:
                            pass
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        self._listeners: list[Callable[[str], None]] = []
        self.version = 0
        self.load()

    # ------------------------------------------------------------------ persistence
    def _file(self, kind: str) -> Path:
        return self.directory / FILES[kind]

    def load(self) -> None:
        with self._lock:
            settings = self._read(self._file("settings"))
            gestures = self._read(self._file("gestures"))
            data = _merge(DEFAULT_SETTINGS, settings)
            data.update(_merge(DEFAULT_GESTURES, gestures))
            _clamp_ranges(data)
            _validate_mappings(data)
            self._data = data
            self.version += 1
        # Write back so new keys appear in the files and corrupt files are repaired.
        self.save()

    @staticmethod
    def _read(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            log.error("Could not read %s (%s); using defaults", path, exc)
            try:
                path.replace(path.with_suffix(".corrupt.json"))
            except OSError:
                pass
            return {}

    def save(self) -> None:
        with self._lock:
            settings = {k: v for k, v in self._data.items() if k in DEFAULT_SETTINGS}
            gestures = {"gestures": self._data["gestures"]}
            self._write(self._file("settings"), settings)
            self._write(self._file("gestures"), gestures)

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        tmp = path.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, path)
        except OSError as exc:
            log.error("Could not save %s: %s", path, exc)

    # ------------------------------------------------------------------ access
    def get(self, path: str, default: Any = None) -> Any:
        with self._lock:
            node: Any = self._data
            for part in path.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return copy.deepcopy(node)

    def set(self, path: str, value: Any, save: bool = True) -> None:
        with self._lock:
            parts = path.split(".")
            node = self._data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            if node.get(parts[-1]) == value:
                return
            node[parts[-1]] = value
            _clamp_ranges(self._data)
            _validate_mappings(self._data)
            self.version += 1
        if save:
            self.save()
        self._notify(path)

    def snapshot(self) -> dict[str, Any]:
        """Deep copy of all settings - safe to hand to another thread."""
        with self._lock:
            return copy.deepcopy(self._data)

    def reset(self, section: str | None = None) -> None:
        with self._lock:
            defaults = copy.deepcopy(DEFAULT_SETTINGS)
            defaults.update(copy.deepcopy(DEFAULT_GESTURES))
            if section is None:
                self._data = defaults
            else:
                self._data[section] = defaults[section]
            self.version += 1
        self.save()
        self._notify(section or "")

    # ------------------------------------------------------------------ observers
    def add_listener(self, callback: Callable[[str], None]) -> None:
        self._listeners.append(callback)

    def _notify(self, path: str) -> None:
        for callback in list(self._listeners):
            try:
                callback(path)
            except Exception:  # pragma: no cover - listener errors must not break saving
                log.exception("Settings listener failed")
