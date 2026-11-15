"""Synthetic hand landmarks.

Generates anatomically plausible 21-point hands for any finger configuration. Used by the unit
tests (so gesture logic is verified without a camera) and by the screenshot tool.
"""
from __future__ import annotations

import math

import numpy as np

# Knuckle (MCP) offsets from the wrist, in hand sizes, for a right hand with the palm facing the
# camera in a mirrored image (thumb on the image-left). y grows downwards, z towards the viewer
# is negative (MediaPipe convention).
_MCP = {
    "index": (-0.30, -0.95),
    "middle": (-0.05, -1.00),
    "ring": (0.18, -0.95),
    "pinky": (0.38, -0.84),
}
_SEGMENTS = {
    "index": (0.45, 0.27, 0.22),
    "middle": (0.50, 0.30, 0.24),
    "ring": (0.46, 0.28, 0.22),
    "pinky": (0.36, 0.22, 0.20),
}
_FAN = {"index": -8.0, "middle": -1.0, "ring": 6.0, "pinky": 13.0}  # degrees from vertical
_BENDS = {  # MCP, PIP, DIP flexion in degrees
    "extended": (0.0, 3.0, 2.0),
    "partial": (25.0, 45.0, 30.0),
    "folded": (75.0, 100.0, 65.0),
    "pinch": (30.0, 35.0, 20.0),
}
_IDX = {"index": 5, "middle": 9, "ring": 13, "pinky": 17}


def _finger_chain(finger: str, state: str, spread: float) -> list[np.ndarray]:
    mx, my = _MCP[finger]
    base = np.array([mx, my, 0.0])
    fan = math.radians(_FAN[finger] * spread)
    d0 = np.array([math.sin(fan), -math.cos(fan), 0.0])
    toward_camera = np.array([0.0, 0.0, -1.0])
    pts = [base]
    phi = 0.0
    for length, bend in zip(_SEGMENTS[finger], _BENDS[state]):
        phi += math.radians(bend)
        d = math.cos(phi) * d0 + math.sin(phi) * toward_camera
        pts.append(pts[-1] + d * length)
    return pts  # MCP, PIP, DIP, TIP


def synth_hand(
    fingers: dict[str, str] | None = None,
    thumb: str = "extended",
    center: tuple[float, float] = (0.5, 0.75),
    size: float = 0.22,
    aspect: float = 4 / 3,
    spread: float = 1.0,
    hand: str = "Right",
    palm_facing: bool = True,
    finger_together: bool = False,
    tilt: float = 0.0,
) -> np.ndarray:
    """Return a (21, 3) array of normalised landmarks.

    ``fingers`` maps index/middle/ring/pinky to ``extended`` | ``partial`` | ``folded`` | ``pinch``.
    ``thumb`` is ``extended`` | ``partial`` | ``folded`` | ``pinch_index`` | ``pinch_middle`` |
    ``pinch_ring`` | ``pinch_pinky``. ``center`` is the wrist position (normalised).
    """
    states = {"index": "extended", "middle": "extended", "ring": "extended", "pinky": "extended"}
    if fingers:
        states.update(fingers)
    if thumb.startswith("pinch_"):
        target = thumb.split("_", 1)[1]
        if states.get(target) in (None, "extended"):
            states[target] = "pinch"

    local = np.zeros((21, 3))
    for finger, state in states.items():
        chain = _finger_chain(finger, state, 0.0 if finger_together else spread)
        for k, p in enumerate(chain):
            local[_IDX[finger] + k] = p
    if finger_together:
        # pull index and middle tips together (scroll gesture "two fingers together")
        for k in range(1, 4):
            mid = (local[5 + k] + local[9 + k]) / 2
            local[5 + k][0] = mid[0] - 0.08
            local[9 + k][0] = mid[0] + 0.08

    # Thumb
    cmc = np.array([-0.25, -0.22, 0.0])
    if thumb == "extended":
        mcp, ip, tip = np.array([-0.48, -0.40, -0.02]), np.array([-0.66, -0.56, -0.04]), np.array([-0.82, -0.70, -0.05])
    elif thumb == "partial":
        mcp, ip, tip = np.array([-0.42, -0.42, -0.05]), np.array([-0.50, -0.62, -0.12]), np.array([-0.52, -0.80, -0.16])
    elif thumb == "folded":
        mcp, ip, tip = np.array([-0.32, -0.48, -0.10]), np.array([-0.18, -0.62, -0.16]), np.array([-0.02, -0.72, -0.16])
    else:
        target = thumb.split("_", 1)[1]
        target_tip = local[_IDX[target] + 3]
        tip = target_tip + np.array([-0.04, 0.03, 0.0])
        mcp = np.array([-0.45, -0.45, -0.05])
        ip = (mcp + tip) / 2 + np.array([-0.08, 0.0, 0.0])
    local[1], local[2], local[3], local[4] = cmc, mcp, ip, tip

    if not palm_facing:
        local[:, 0] *= -1  # back of the hand: thumb appears on the other side
        local[:, 2] *= -1
    if hand == "Left":
        local[:, 0] *= -1
    if tilt:
        # rotate the whole hand in the image plane around the wrist (positive = clockwise on screen)
        a = math.radians(tilt)
        x, y = local[:, 0].copy(), local[:, 1].copy()
        local[:, 0] = x * math.cos(a) - y * math.sin(a)
        local[:, 1] = x * math.sin(a) + y * math.cos(a)

    out = np.zeros((21, 3))
    out[:, 0] = center[0] + local[:, 0] * size / aspect
    out[:, 1] = center[1] + local[:, 1] * size
    out[:, 2] = local[:, 2] * size / aspect
    return out


POSES: dict[str, dict] = {
    "point": dict(fingers={"middle": "folded", "ring": "folded", "pinky": "folded"}, thumb="folded"),
    "open_palm": dict(),
    "fist": dict(fingers={"index": "folded", "middle": "folded", "ring": "folded", "pinky": "folded"}, thumb="folded"),
    "pinch_index": dict(fingers={"middle": "folded", "ring": "folded", "pinky": "folded"}, thumb="pinch_index"),
    "pinch_middle": dict(fingers={"index": "extended", "ring": "folded", "pinky": "folded"}, thumb="pinch_middle"),
    "pinch_pinky": dict(fingers={"index": "folded", "middle": "folded", "ring": "folded"}, thumb="pinch_pinky"),
    "two_finger": dict(fingers={"ring": "folded", "pinky": "folded"}, thumb="folded", finger_together=True),
    "v_sign": dict(fingers={"ring": "folded", "pinky": "folded"}, thumb="folded", spread=3.0),
    "three_finger": dict(fingers={"pinky": "folded"}, thumb="folded"),
    "thumb_index_middle": dict(fingers={"ring": "folded", "pinky": "folded"}, thumb="extended"),
    "four_finger": dict(thumb="folded"),
    "horns": dict(fingers={"middle": "folded", "ring": "folded"}, thumb="folded"),
}


def pose_landmarks(name: str, **overrides) -> np.ndarray:
    params = dict(POSES[name])
    params.update(overrides)
    return synth_hand(**params)
