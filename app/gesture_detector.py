"""Finger-state and hand-feature extraction.

Everything here is pure computation on landmark arrays, so it is fully unit-testable without a
camera. Distances are expressed in *hand sizes* (wrist -> middle-finger knuckle) so thresholds do
not depend on how far the hand is from the camera.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from app.hand_tracker import (
    INDEX_DIP, INDEX_MCP, INDEX_PIP, INDEX_TIP, MIDDLE_DIP, MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP,
    PINKY_DIP, PINKY_MCP, PINKY_PIP, PINKY_TIP, RING_DIP, RING_MCP, RING_PIP, RING_TIP,
    THUMB_CMC, THUMB_IP, THUMB_MCP, THUMB_TIP, WRIST,
)


class FingerState(str, Enum):
    EXTENDED = "extended"
    PARTIAL = "partial"
    FOLDED = "folded"


FINGERS = ("thumb", "index", "middle", "ring", "pinky")

_FINGER_JOINTS = {
    "index": (INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP),
    "middle": (MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP),
    "ring": (RING_MCP, RING_PIP, RING_DIP, RING_TIP),
    "pinky": (PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP),
}
TIPS = {"thumb": THUMB_TIP, "index": INDEX_TIP, "middle": MIDDLE_TIP, "ring": RING_TIP, "pinky": PINKY_TIP}

# Curl thresholds (sum of PIP + DIP bend angles, degrees)
EXTENDED_MAX_CURL = 65.0
FOLDED_MIN_CURL = 120.0
MOVING_SPEED = 1.2  # hand sizes per second


@dataclass
class HandFeatures:
    points: np.ndarray  # (21, 3) aspect-corrected coordinates (units: frame height)
    norm: np.ndarray  # (21, 3) original normalised landmarks (x, y in [0, 1])
    handedness: str
    score: float
    hand_size: float
    fingers: dict[str, FingerState]
    curl: dict[str, float]
    pinch: dict[str, float]  # thumb tip -> finger tip distance in hand sizes
    index_middle_gap: float  # hand sizes
    spread: float  # mean gap between adjacent fingertips, hand sizes
    palm_center: np.ndarray  # normalised (x, y)
    palm_facing: bool
    aspect: float = 4 / 3
    speed: float = 0.0  # palm speed, hand sizes per second
    tip_speed: dict[str, float] = field(default_factory=dict)

    # convenience -------------------------------------------------------------------
    def is_extended(self, finger: str) -> bool:
        return self.fingers[finger] == FingerState.EXTENDED

    def is_folded(self, finger: str) -> bool:
        return self.fingers[finger] == FingerState.FOLDED

    def touching(self, finger: str, threshold: float) -> bool:
        """True when the thumb tip touches ``finger``'s tip (distance below ``threshold``)."""
        return self.pinch[finger] < threshold

    @property
    def moving(self) -> bool:
        return self.speed > MOVING_SPEED

    @property
    def stationary(self) -> bool:
        return not self.moving

    def finger_moving(self, finger: str) -> bool:
        return self.tip_speed.get(finger, 0.0) > MOVING_SPEED

    def tip(self, finger: str) -> np.ndarray:
        """Normalised (x, y) of a fingertip."""
        return self.norm[TIPS[finger], :2]

    @property
    def index_tip(self) -> np.ndarray:
        return self.norm[INDEX_TIP, :2]

    @property
    def anchor(self) -> np.ndarray:
        """A point that moves with the hand but not with finger flexion (index knuckle).

        Used for relative cursor motion while pinching so that closing the pinch itself does not
        drag the cursor.
        """
        return self.norm[INDEX_MCP, :2]

    @property
    def scroll_point(self) -> np.ndarray:
        return (self.norm[INDEX_TIP, :2] + self.norm[MIDDLE_TIP, :2]) / 2.0


def _angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Bend angle at ``b`` in degrees (0 = straight line a-b-c)."""
    v1 = b - a
    v2 = c - b
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cos = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def to_points(landmarks: np.ndarray, aspect: float) -> np.ndarray:
    """Convert normalised landmarks to an isotropic space (units of frame height)."""
    pts = np.asarray(landmarks, dtype=np.float64).copy()
    pts[:, 0] *= aspect
    pts[:, 2] *= aspect  # MediaPipe z uses roughly the same scale as x
    return pts


def finger_curl(pts: np.ndarray, finger: str) -> float:
    if finger == "thumb":
        return _angle(pts[THUMB_CMC], pts[THUMB_MCP], pts[THUMB_IP]) + _angle(pts[THUMB_MCP], pts[THUMB_IP], pts[THUMB_TIP])
    mcp, pip, dip, tip = _FINGER_JOINTS[finger]
    return _angle(pts[mcp], pts[pip], pts[dip]) + _angle(pts[pip], pts[dip], pts[tip])


def finger_state(pts: np.ndarray, finger: str, hand_size: float) -> tuple[FingerState, float]:
    curl = finger_curl(pts, finger)
    if finger == "thumb":
        # The thumb is judged by how far its tip sits from the palm as well as its curl.
        away = np.linalg.norm(pts[THUMB_TIP] - pts[INDEX_MCP]) / hand_size
        tucked = np.linalg.norm(pts[THUMB_TIP] - pts[MIDDLE_MCP]) / hand_size
        if tucked < 0.45 or away < 0.3:
            return FingerState.FOLDED, curl
        if away > 0.55 and curl < 70:
            return FingerState.EXTENDED, curl
        return FingerState.PARTIAL, curl
    mcp, pip, _dip, tip = _FINGER_JOINTS[finger]
    wrist = pts[WRIST]
    tip_dist = np.linalg.norm(pts[tip] - wrist)
    pip_dist = np.linalg.norm(pts[pip] - wrist)
    if curl >= FOLDED_MIN_CURL or tip_dist < pip_dist * 0.95:
        return FingerState.FOLDED, curl
    if curl <= EXTENDED_MAX_CURL and tip_dist > pip_dist * 1.1:
        return FingerState.EXTENDED, curl
    return FingerState.PARTIAL, curl


def palm_normal_z(pts: np.ndarray) -> float:
    a = pts[INDEX_MCP] - pts[WRIST]
    b = pts[PINKY_MCP] - pts[WRIST]
    return float(a[0] * b[1] - a[1] * b[0])


def extract_features(
    landmarks: np.ndarray,
    handedness: str = "Right",
    score: float = 1.0,
    aspect: float = 4 / 3,
    mirrored: bool = True,
) -> HandFeatures:
    norm = np.asarray(landmarks, dtype=np.float64)
    pts = to_points(norm, aspect)
    hand_size = float(np.linalg.norm(pts[MIDDLE_MCP] - pts[WRIST]))
    hand_size = max(hand_size, 1e-4)

    fingers: dict[str, FingerState] = {}
    curl: dict[str, float] = {}
    for name in FINGERS:
        fingers[name], curl[name] = finger_state(pts, name, hand_size)

    thumb = pts[THUMB_TIP]
    pinch = {name: float(np.linalg.norm(thumb - pts[TIPS[name]]) / hand_size) for name in FINGERS[1:]}

    tips = [pts[TIPS[n]][:2] for n in FINGERS[1:]]
    gaps = [np.linalg.norm(tips[i] - tips[i + 1]) / hand_size for i in range(3)]
    palm_idx = [WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP]
    palm_center = norm[palm_idx, :2].mean(axis=0)

    # In a mirrored image a right palm facing the camera has a positive cross product z.
    nz = palm_normal_z(pts)
    expected = 1.0 if handedness == "Right" else -1.0
    if not mirrored:
        expected = -expected
    palm_facing = nz * expected > 0

    return HandFeatures(
        points=pts,
        norm=norm,
        handedness=handedness,
        score=score,
        hand_size=hand_size,
        fingers=fingers,
        curl=curl,
        pinch=pinch,
        index_middle_gap=float(gaps[0]),
        spread=float(np.mean(gaps)),
        palm_center=palm_center,
        palm_facing=palm_facing,
        aspect=aspect,
    )


class MotionTracker:
    """Adds palm / fingertip velocity (in hand sizes per second) to successive features."""

    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha
        self._prev: HandFeatures | None = None
        self._prev_t = 0.0
        self._speed = 0.0
        self._tip_speed: dict[str, float] = {}

    def reset(self) -> None:
        self._prev = None
        self._speed = 0.0
        self._tip_speed = {}

    def update(self, features: HandFeatures | None, t: float) -> None:
        if features is None:
            self.reset()
            return
        if self._prev is not None and t > self._prev_t:
            dt = t - self._prev_t
            hs = features.hand_size
            palm_now = features.points[[WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP], :2].mean(axis=0)
            palm_prev = self._prev.points[[WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP], :2].mean(axis=0)
            inst = float(np.linalg.norm(palm_now - palm_prev) / hs / dt)
            self._speed = self.alpha * inst + (1 - self.alpha) * self._speed
            for name, idx in TIPS.items():
                v = float(np.linalg.norm(features.points[idx, :2] - self._prev.points[idx, :2]) / hs / dt)
                self._tip_speed[name] = self.alpha * v + (1 - self.alpha) * self._tip_speed.get(name, 0.0)
        features.speed = self._speed
        features.tip_speed = dict(self._tip_speed)
        self._prev = features
        self._prev_t = t
