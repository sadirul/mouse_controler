"""Static hand-pose classification and temporal debouncing.

``PoseClassifier`` maps one frame of :class:`HandFeatures` to a :class:`Pose` (with pinch
hysteresis). ``PoseStabilizer`` only reports a pose after it has been seen continuously for its
configured minimum detection duration, which removes single-frame glitches.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from app.gesture_detector import FingerState, HandFeatures


class Pose(str, Enum):
    NONE = "none"  # no (usable) hand
    RELAXED = "relaxed"  # a hand, but no recognised pose
    FIST = "fist"
    POINT = "point"
    PINCH_INDEX = "pinch_index"
    PINCH_MIDDLE = "pinch_middle"
    PINCH_PINKY = "pinch_pinky"
    TWO_FINGER = "two_finger"
    THREE_FINGER = "three_finger"
    THUMB_INDEX_MIDDLE = "thumb_index_middle"
    FOUR_FINGER = "four_finger"
    OPEN_PALM = "open_palm"
    HORNS = "horns"


POSE_LABELS = {
    Pose.NONE: "No hand",
    Pose.RELAXED: "Relaxed hand",
    Pose.FIST: "Fist (clutch)",
    Pose.POINT: "Index pointer",
    Pose.PINCH_INDEX: "Thumb + index pinch",
    Pose.PINCH_MIDDLE: "Thumb + middle pinch",
    Pose.PINCH_PINKY: "Thumb + pinky pinch",
    Pose.TWO_FINGER: "Two fingers",
    Pose.THREE_FINGER: "Three fingers",
    Pose.THUMB_INDEX_MIDDLE: "Thumb + two fingers",
    Pose.FOUR_FINGER: "Four fingers",
    Pose.OPEN_PALM: "Open palm",
    Pose.HORNS: "Horns (index + pinky)",
}


class PoseClassifier:
    def __init__(self, gestures_cfg: dict[str, Any] | None = None):
        self.cfg: dict[str, Any] = {}
        self.configure(gestures_cfg or {})
        self.reset()

    def configure(self, gestures_cfg: dict[str, Any]) -> None:
        click = gestures_cfg.get("click", {})
        self.pinch_on = float(click.get("pinch_threshold", 0.28))
        self.pinch_off = max(float(click.get("release_threshold", 0.38)), self.pinch_on + 0.02)
        self.middle_on = float(gestures_cfg.get("right_click", {}).get("pinch_threshold", 0.28))
        self.pinky_on = float(gestures_cfg.get("thumb_pinky", {}).get("pinch_threshold", 0.32))
        scroll = gestures_cfg.get("scroll", {})
        self.require_together = bool(scroll.get("require_together", True))
        self.together_threshold = float(scroll.get("together_threshold", 0.45))
        self.cfg = gestures_cfg

    def reset(self) -> None:
        self._pinch_index = False
        self._pinch_middle = False
        self._pinch_pinky = False

    def _hysteresis(self, active: bool, value: float, on: float) -> bool:
        off = on * (self.pinch_off / self.pinch_on)
        return value < off if active else value < on

    def classify(self, f: HandFeatures | None) -> Pose:
        if f is None:
            self.reset()
            return Pose.NONE

        ext = f.is_extended
        folded = f.is_folded

        # --- pinches (a pinched finger is never fully folded: that would be a fist) ----------
        self._pinch_index = (not folded("index")) and self._hysteresis(self._pinch_index, f.pinch["index"], self.pinch_on)
        self._pinch_middle = (not folded("middle")) and self._hysteresis(self._pinch_middle, f.pinch["middle"], self.middle_on)
        self._pinch_pinky = (not folded("pinky")) and self._hysteresis(self._pinch_pinky, f.pinch["pinky"], self.pinky_on)

        if self._pinch_index and f.pinch["index"] <= f.pinch["middle"]:
            return Pose.PINCH_INDEX
        if self._pinch_middle and f.pinch["index"] > self.pinch_off:
            return Pose.PINCH_MIDDLE
        if (
            self._pinch_pinky
            and f.pinch["index"] > self.pinch_off
            and f.pinch["middle"] > self.middle_on * 1.3
            and f.pinch["ring"] > f.pinch["pinky"]
        ):
            return Pose.PINCH_PINKY

        four = all(ext(n) for n in ("index", "middle", "ring", "pinky"))
        if four:
            # Thumb tucked -> four fingers (window swipes). Otherwise treat as open palm, which is
            # the safe interpretation (it can only ever stop control).
            return Pose.FOUR_FINGER if folded("thumb") else Pose.OPEN_PALM

        index, middle, ring, pinky = ext("index"), ext("middle"), ext("ring"), ext("pinky")
        if index and middle and ring and not pinky:
            return Pose.THREE_FINGER
        if index and middle and not ring and not pinky:
            thumb_out = f.fingers["thumb"] == FingerState.EXTENDED
            if thumb_out and self.cfg.get("window_move", {}).get("pose") == "thumb_index_middle":
                return Pose.THUMB_INDEX_MIDDLE
            if self.require_together_ok(f):
                return Pose.TWO_FINGER
            return Pose.RELAXED  # e.g. a spread "V" sign - deliberately ignored
        if index and pinky and folded("middle") and folded("ring"):
            return Pose.HORNS
        if index and not middle and not ring:
            return Pose.POINT
        if all(folded(n) for n in ("index", "middle", "ring", "pinky")):
            return Pose.FIST
        return Pose.RELAXED

    def require_together_ok(self, f: HandFeatures) -> bool:
        return (not self.require_together) or f.index_middle_gap <= self.together_threshold


# Default minimum detection durations in milliseconds (overridable via gestures.json)
DEFAULT_MIN_MS = {
    Pose.NONE: 250,
    Pose.RELAXED: 80,
    Pose.FIST: 80,
    Pose.POINT: 40,
    Pose.PINCH_INDEX: 40,
    Pose.PINCH_MIDDLE: 80,
    Pose.PINCH_PINKY: 80,
    Pose.TWO_FINGER: 120,
    Pose.THREE_FINGER: 250,
    Pose.THUMB_INDEX_MIDDLE: 250,
    Pose.FOUR_FINGER: 80,
    Pose.OPEN_PALM: 100,
    Pose.HORNS: 150,
}

_CFG_KEYS = {
    Pose.POINT: ("move", "min_ms"),
    Pose.PINCH_INDEX: ("click", "min_ms"),
    Pose.PINCH_MIDDLE: ("right_click", "min_ms"),
    Pose.TWO_FINGER: ("scroll", "min_ms"),
    Pose.THREE_FINGER: ("window_move", "min_ms"),
    Pose.THUMB_INDEX_MIDDLE: ("window_move", "min_ms"),
    Pose.FOUR_FINGER: ("window_swipe", "min_ms"),
}


class PoseStabilizer:
    """Debounce poses: a new pose becomes current only after persisting ``min_ms``."""

    def __init__(self, gestures_cfg: dict[str, Any] | None = None):
        self.min_ms = dict(DEFAULT_MIN_MS)
        self.configure(gestures_cfg or {})
        self.reset()

    def configure(self, gestures_cfg: dict[str, Any]) -> None:
        self.min_ms = dict(DEFAULT_MIN_MS)
        for pose, (section, key) in _CFG_KEYS.items():
            value = gestures_cfg.get(section, {}).get(key)
            if isinstance(value, (int, float)):
                self.min_ms[pose] = float(value)

    def reset(self) -> None:
        self.stable = Pose.NONE
        self._candidate = Pose.NONE
        self._since = 0.0

    def update(self, pose: Pose, t: float) -> Pose:
        if pose == self.stable:
            self._candidate = pose
            self._since = t
            return self.stable
        if pose != self._candidate:
            self._candidate = pose
            self._since = t
        if (t - self._since) * 1000.0 >= self.min_ms.get(pose, 0):
            self.stable = pose
        return self.stable
