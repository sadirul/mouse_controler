"""Draws hand landmarks and gesture feedback onto preview frames (in place, no extra copies)."""
from __future__ import annotations

import cv2
import numpy as np

from app.gesture_state import State
from app.hand_tracker import HAND_CONNECTIONS, INDEX_TIP, THUMB_TIP

# BGR colours per state
STATE_COLORS = {
    State.IDLE: (180, 170, 160),
    State.POINTING: (255, 200, 80),  # cyan-ish blue
    State.PINCH: (80, 220, 255),  # amber
    State.DRAGGING: (60, 140, 255),  # orange
    State.WAIT_RELEASE: (200, 200, 200),
    State.RIGHT_PINCH: (230, 120, 230),  # magenta
    State.SCROLLING: (120, 230, 120),  # green
    State.WINDOW_MOVING: (255, 140, 140),  # violet
    State.SWIPE: (255, 255, 120),
    State.HOLD_POSE: (120, 200, 255),
    State.STOPPED: (60, 60, 235),  # red
}


def _text(img, text, org, scale=0.6, color=(255, 255, 255), thickness=1):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 3, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def draw_overlay(
    frame: np.ndarray,
    landmarks: np.ndarray | None,
    state: State,
    label: str,
    confidence: float | None,
    region: tuple[float, float, float, float] | None,
    progress: float = 0.0,
    progress_label: str = "",
    paused: bool = False,
    other_hands: list[np.ndarray] | None = None,
) -> np.ndarray:
    h, w = frame.shape[:2]
    color = STATE_COLORS.get(state, (255, 255, 255))

    if region is not None:
        x0, y0, x1, y1 = region
        p0 = (int(max(x0, 0) * w), int(max(y0, 0) * h))
        p1 = (int(min(x1, 1) * w), int(min(y1, 1) * h))
        cv2.rectangle(frame, p0, p1, (110, 110, 110), 1, cv2.LINE_AA)
        _text(frame, "active area", (p0[0] + 4, p0[1] + 14), 0.4, (170, 170, 170))

    for lms in other_hands or []:
        pts = (lms[:, :2] * (w, h)).astype(int)
        for a, b in HAND_CONNECTIONS:
            cv2.line(frame, tuple(pts[a]), tuple(pts[b]), (90, 90, 90), 1, cv2.LINE_AA)

    if landmarks is not None:
        pts = (landmarks[:, :2] * (w, h)).astype(int)
        for a, b in HAND_CONNECTIONS:
            cv2.line(frame, tuple(pts[a]), tuple(pts[b]), color, 2, cv2.LINE_AA)
        for i, p in enumerate(pts):
            cv2.circle(frame, tuple(p), 3, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(frame, tuple(pts[INDEX_TIP]), 11, (255, 220, 0), 2, cv2.LINE_AA)
        cv2.circle(frame, tuple(pts[INDEX_TIP]), 4, (255, 220, 0), -1, cv2.LINE_AA)
        cv2.circle(frame, tuple(pts[THUMB_TIP]), 9, (0, 165, 255), 2, cv2.LINE_AA)

        if progress > 0.02:
            center = tuple(pts[[0, 5, 9, 13, 17]].mean(axis=0).astype(int))
            radius = max(18, int(np.linalg.norm(pts[9] - pts[0]) * 0.55))
            cv2.circle(frame, center, radius, (70, 70, 70), 3, cv2.LINE_AA)
            ring = (60, 60, 235) if progress_label == "Emergency stop" else (80, 220, 255)
            cv2.ellipse(frame, center, (radius, radius), -90, 0, int(360 * min(progress, 1.0)), ring, 4, cv2.LINE_AA)
            if progress_label:
                _text(frame, progress_label, (center[0] - radius, center[1] + radius + 20), 0.5, ring)

    # status banner
    banner = label or "-"
    if confidence is not None:
        banner = f"{banner}   ({confidence * 100:.0f}%)"
    cv2.rectangle(frame, (0, 0), (w, 30), (20, 20, 20), -1)
    cv2.circle(frame, (14, 15), 6, color, -1, cv2.LINE_AA)
    _text(frame, banner, (28, 21), 0.55, (240, 240, 240))

    if state == State.STOPPED:
        cv2.rectangle(frame, (2, 2), (w - 3, h - 3), (60, 60, 235), 4)
        _text(frame, "EMERGENCY STOP", (w // 2 - 120, h - 20), 0.9, (80, 80, 255), 2)
    elif paused:
        cv2.rectangle(frame, (2, 2), (w - 3, h - 3), (0, 200, 255), 3)
        _text(frame, "PAUSED", (w // 2 - 50, h - 20), 0.9, (0, 200, 255), 2)
    return frame
