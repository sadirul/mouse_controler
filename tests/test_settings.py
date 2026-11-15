"""Settings persistence, defaults merging and validation."""
from __future__ import annotations

import json

from app.settings_manager import DEFAULT_GESTURES, DEFAULT_SETTINGS, SettingsManager


def test_defaults_created(tmp_path):
    sm = SettingsManager(tmp_path)
    assert (tmp_path / "settings.json").exists()
    assert (tmp_path / "gestures.json").exists()
    assert sm.get("cursor.speed") == DEFAULT_SETTINGS["cursor"]["speed"]
    assert sm.get("gestures.long_press.duration_ms") == 800
    assert sm.get("gestures.emergency_stop.hold_ms") == 1500


def test_persistence_between_sessions(tmp_path):
    sm = SettingsManager(tmp_path)
    sm.set("cursor.smoothing", 0.8)
    sm.set("gestures.click.pinch_threshold", 0.3)
    sm.set("tracking.preferred_hand", "left")
    sm.set("gestures.mappings.horns_hold", "minimize")
    again = SettingsManager(tmp_path)
    assert again.get("cursor.smoothing") == 0.8
    assert again.get("gestures.click.pinch_threshold") == 0.3
    assert again.get("tracking.preferred_hand") == "left"
    assert again.get("gestures.mappings.horns_hold") == "minimize"


def test_partial_file_merged_with_defaults(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"cursor": {"speed": 2.0}}))
    sm = SettingsManager(tmp_path)
    assert sm.get("cursor.speed") == 2.0
    assert sm.get("cursor.smoothing") == DEFAULT_SETTINGS["cursor"]["smoothing"]
    assert sm.get("camera.device") == 0


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    (tmp_path / "gestures.json").write_text("{not json")
    sm = SettingsManager(tmp_path)
    assert sm.get("gestures.click.enabled") is True
    assert (tmp_path / "gestures.corrupt.json").exists()


def test_wrong_types_and_ranges_are_repaired(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"cursor": {"speed": "fast", "smoothing": 7}}))
    (tmp_path / "gestures.json").write_text(json.dumps({"gestures": {"double_click": {"interval_ms": 5}}}))
    sm = SettingsManager(tmp_path)
    assert sm.get("cursor.speed") == DEFAULT_SETTINGS["cursor"]["speed"]
    assert sm.get("cursor.smoothing") == 1.0
    assert sm.get("gestures.double_click.interval_ms") == 100


def test_invalid_mapping_rejected(tmp_path):
    (tmp_path / "gestures.json").write_text(
        json.dumps({"gestures": {"mappings": {"horns_hold": "rm -rf /", "bogus": "close"}}})
    )
    sm = SettingsManager(tmp_path)
    assert sm.get("gestures.mappings.horns_hold") == DEFAULT_GESTURES["gestures"]["mappings"]["horns_hold"]
    assert "bogus" not in sm.get("gestures.mappings")


def test_listeners_and_version(tmp_path):
    sm = SettingsManager(tmp_path)
    seen = []
    sm.add_listener(seen.append)
    v = sm.version
    sm.set("cursor.speed", 1.5)
    sm.set("cursor.speed", 1.5)  # unchanged value: no notification
    assert seen == ["cursor.speed"]
    assert sm.version == v + 1


def test_reset_section(tmp_path):
    sm = SettingsManager(tmp_path)
    sm.set("cursor.speed", 3.0)
    sm.set("camera.device", 2)
    sm.reset("cursor")
    assert sm.get("cursor.speed") == DEFAULT_SETTINGS["cursor"]["speed"]
    assert sm.get("camera.device") == 2


def test_snapshot_is_independent(tmp_path):
    sm = SettingsManager(tmp_path)
    snap = sm.snapshot()
    snap["cursor"]["speed"] = 9
    assert sm.get("cursor.speed") != 9
