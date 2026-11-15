"""MediaPipe Hand Landmarker wrapper (21 landmarks per hand)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger(__name__)

# Landmark indices (MediaPipe hand model)
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20

LANDMARK_NAMES = [
    "wrist",
    "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
    "index_mcp", "index_pip", "index_dip", "index_tip",
    "middle_mcp", "middle_pip", "middle_dip", "middle_tip",
    "ring_mcp", "ring_pip", "ring_dip", "ring_tip",
    "pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip",
]

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
]


@dataclass
class TrackedHand:
    landmarks: np.ndarray  # (21, 3) normalised image coordinates: x, y in [0, 1], z relative depth
    handedness: str  # "Right" or "Left" (the user's actual hand)
    score: float  # handedness confidence


class HandTrackerError(RuntimeError):
    pass


class HandTracker:
    def __init__(
        self,
        model_path: str,
        num_hands: int = 2,
        min_detection_confidence: float = 0.6,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        try:
            from mediapipe.tasks.python import BaseOptions, vision
            import mediapipe as mp
        except Exception as exc:  # pragma: no cover - depends on installation
            raise HandTrackerError(f"MediaPipe could not be imported: {exc}") from exc
        self._mp = mp
        try:
            # Load from a buffer: works with non-ASCII install paths and inside PyInstaller bundles.
            with open(model_path, "rb") as fh:
                model = fh.read()
        except OSError as exc:
            raise HandTrackerError(f"Hand model not found at {model_path}: {exc}") from exc
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=model),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        try:
            self._landmarker = vision.HandLandmarker.create_from_options(options)
        except Exception as exc:
            raise HandTrackerError(f"MediaPipe initialisation failed: {exc}") from exc
        self._last_ts = 0
        log.info("Hand landmarker initialised")

    def process(self, frame_bgr: np.ndarray, mirrored: bool = True) -> list[TrackedHand]:
        """Detect hands in a BGR frame.

        MediaPipe labels handedness assuming a mirrored (selfie) image. When the camera image is
        not mirrored the labels are swapped so ``handedness`` always names the user's real hand.
        """
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        ts = int(time.monotonic() * 1000)
        if ts <= self._last_ts:
            ts = self._last_ts + 1
        self._last_ts = ts
        result = self._landmarker.detect_for_video(image, ts)
        hands: list[TrackedHand] = []
        for lms, handed in zip(result.hand_landmarks, result.handedness):
            arr = np.array([(p.x, p.y, p.z) for p in lms], dtype=np.float64)
            label = handed[0].category_name if handed else "Right"
            score = float(handed[0].score) if handed else 0.0
            if not mirrored:
                label = "Left" if label == "Right" else "Right"
            hands.append(TrackedHand(arr, label, score))
        return hands

    def close(self) -> None:
        try:
            self._landmarker.close()
        except Exception:  # pragma: no cover
            pass


def select_hand(hands: list[TrackedHand], preferred: str, min_score: float = 0.0) -> TrackedHand | None:
    """Pick the controlling hand. ``preferred`` is "right", "left" or "any"."""
    candidates = [h for h in hands if h.score >= min_score] or []
    if not candidates:
        return None
    if preferred in ("right", "left"):
        wanted = preferred.capitalize()
        matching = [h for h in candidates if h.handedness == wanted]
        if not matching:
            return None
        return max(matching, key=lambda h: h.score)
    return max(candidates, key=lambda h: h.score)
