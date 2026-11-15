"""Two-hand gestures.

* Camera frame -> screenshot: an L with each hand (thumb and index finger extended, the other
  fingers folded), as if framing a photo.
* Crossed index fingers (an X) -> configurable action, by default lock Windows.

Detection is pure computation on :class:`HandFeatures`, so it is unit-tested without a camera;
the screenshot itself uses Pillow's ``ImageGrab``.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.gesture_detector import FingerState, HandFeatures
from app.hand_tracker import INDEX_MCP, INDEX_TIP

# Short tracking gaps (a missed frame) do not cancel the hold.
_GAP_TOLERANCE_S = 0.15
# The two hands must be at least this far apart (in hand sizes) so that one hand that MediaPipe
# reports twice can never trigger the gesture.
_MIN_SEPARATION = 1.0


def is_frame_hand(f: HandFeatures) -> bool:
    """An "L" hand: thumb and index extended, middle / ring / pinky not extended."""
    return (
        f.fingers["index"] == FingerState.EXTENDED
        and f.fingers["thumb"] != FingerState.FOLDED
        and all(f.fingers[n] != FingerState.EXTENDED for n in ("middle", "ring", "pinky"))
    )


def is_pointer_hand(f: HandFeatures) -> bool:
    """Index finger out (straight or slightly bent), middle / ring / pinky not extended."""
    return (
        f.fingers["index"] != FingerState.FOLDED
        and all(f.fingers[n] != FingerState.EXTENDED for n in ("middle", "ring", "pinky"))
    )


def _segments_cross(p1, p2, q1, q2) -> bool:
    """True when segment p1-p2 properly intersects segment q1-q2 (2D)."""
    def orient(a, b, c) -> float:
        return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))

    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 < 0


# The two index fingers must cross at a clear angle, not lie on top of each other.
_MIN_CROSS_ANGLE = 45.0


def is_cross_pose(hands: list[HandFeatures]) -> bool:
    """True when two hands hold their index fingers crossed like an X."""
    pointers = [h for h in hands if is_pointer_hand(h)]
    for i in range(len(pointers)):
        for j in range(i + 1, len(pointers)):
            a, b = pointers[i], pointers[j]
            # both landmark sets are in the same aspect-corrected image space
            p1, p2 = a.points[INDEX_MCP, :2], a.points[INDEX_TIP, :2]
            q1, q2 = b.points[INDEX_MCP, :2], b.points[INDEX_TIP, :2]
            if not _segments_cross(p1, p2, q1, q2):
                continue
            u, v = p2 - p1, q2 - q1
            cos = abs(float(np.dot(u, v))) / max(float(np.linalg.norm(u) * np.linalg.norm(v)), 1e-9)
            if np.degrees(np.arccos(min(cos, 1.0))) >= _MIN_CROSS_ANGLE:
                return True
    return False


def is_frame_pose(hands: list[HandFeatures]) -> bool:
    """True when two separate hands both show the L shape (and are not crossed)."""
    if is_cross_pose(hands):
        return False
    frames = [h for h in hands if is_frame_hand(h)]
    for i in range(len(frames)):
        for j in range(i + 1, len(frames)):
            a, b = frames[i], frames[j]
            gap = np.array([(a.palm_center[0] - b.palm_center[0]) * a.aspect, a.palm_center[1] - b.palm_center[1]])
            size = max(a.hand_size, b.hand_size)
            if np.linalg.norm(gap) / size >= _MIN_SEPARATION:
                return True
    return False


@dataclass
class FrameStatus:
    active: bool = False  # the frame pose is being held (one-hand gestures are suspended)
    progress: float = 0.0
    fired: bool = False  # this frame: take the screenshot now


class FrameGesture:
    """Hold timer with cooldown; fires once per hold (the pose must be released to fire again)."""

    detector = staticmethod(is_frame_pose)

    def __init__(self, cfg: dict[str, Any] | None = None):
        self.configure(cfg or {})
        self.reset()

    def configure(self, cfg: dict[str, Any]) -> None:
        self.enabled = bool(cfg.get("enabled", True))
        self.hold_s = float(cfg.get("hold_ms", 800)) / 1000.0
        self.cooldown_s = float(cfg.get("cooldown_ms", 2000)) / 1000.0

    def reset(self) -> None:
        self._since: float | None = None
        self._last_seen = -1e9
        self._done = False
        self._last_fire = -1e9

    def update(self, hands: list[HandFeatures], t: float) -> FrameStatus:
        if not self.enabled:
            self._since = None
            return FrameStatus()
        if self.detector(hands):
            self._last_seen = t
            if self._since is None:
                self._since = t
        elif self._since is not None and t - self._last_seen > _GAP_TOLERANCE_S:
            self._since = None
            self._done = False
        if self._since is None:
            return FrameStatus()
        if self._done:
            return FrameStatus(active=True, progress=1.0)
        progress = min((t - self._since) / self.hold_s, 1.0) if self.hold_s > 0 else 1.0
        if progress >= 1.0:
            self._done = True
            if t - self._last_fire >= self.cooldown_s:
                self._last_fire = t
                return FrameStatus(active=True, progress=1.0, fired=True)
        return FrameStatus(active=True, progress=progress)


class CrossGesture(FrameGesture):
    """Crossed index fingers held briefly."""

    detector = staticmethod(is_cross_pose)

    def configure(self, cfg: dict[str, Any]) -> None:
        super().configure({"hold_ms": 500, "cooldown_ms": 3000, **cfg})


def default_folder() -> Path:
    return Path.home() / "Pictures" / "Screenshots"


def take_screenshot(folder: str | Path | None = None) -> Path:
    """Capture all monitors and save a PNG. Returns the file path."""
    from PIL import ImageGrab

    target = Path(folder) if folder else default_folder()
    target.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = target / f"Screenshot_{stamp}.png"
    n = 1
    while path.exists():
        n += 1
        path = target / f"Screenshot_{stamp}_{n}.png"
    image = ImageGrab.grab(all_screens=True)
    image.save(path, "PNG")
    return path
