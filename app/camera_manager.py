"""Webcam capture with OpenCV."""
from __future__ import annotations

import logging
import sys
import threading
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)


class CameraError(RuntimeError):
    pass


def _backends() -> list[int]:
    if sys.platform == "win32":
        # Media Foundation delivers full frame rate on most webcams (DirectShow often caps at 15 FPS
        # in YUY2 mode); DirectShow remains as a fallback for older devices.
        return [cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY]
    if sys.platform == "darwin":
        return [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
    return [cv2.CAP_V4L2, cv2.CAP_ANY]


class CameraManager:
    """Owns a single ``cv2.VideoCapture``.

    Frames are grabbed on a dedicated background thread that always keeps only the newest frame.
    Capture (which blocks until the camera delivers the next frame) therefore overlaps with hand
    tracking instead of adding to it, roughly doubling throughput, and stale frames are never
    processed (lower latency).
    """

    def __init__(self, device: int = 0, width: int = 640, height: int = 480, fps: int = 30, mirror: bool = True):
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.mirror = mirror
        self._cap: cv2.VideoCapture | None = None
        self.actual_size = (0, 0)
        self.actual_fps = 0.0
        self._cond = threading.Condition()
        self._frame: np.ndarray | None = None
        self._seq = 0
        self._read_seq = 0
        self._error: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def open(self) -> None:
        self.release()
        for backend in _backends():
            cap = cv2.VideoCapture(self.device, backend)
            if not cap.isOpened():
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok, frame = cap.read()
            if not ok or frame is None:
                cap.release()
                continue
            self._cap = cap
            self.actual_size = (frame.shape[1], frame.shape[0])
            self.actual_fps = cap.get(cv2.CAP_PROP_FPS) or float(self.fps)
            self._error = None
            self._stop.clear()
            self._thread = threading.Thread(target=self._grab_loop, name="camera-grabber", daemon=True)
            self._thread.start()
            log.info("Camera %s opened (backend %s) at %dx%d", self.device, backend, *self.actual_size)
            return
        raise CameraError(
            f"Camera {self.device} could not be opened. Check that it is connected, not used by "
            f"another application, and that camera access is allowed in Windows privacy settings."
        )

    def _grab_loop(self) -> None:
        failures = 0
        cap = self._cap
        while not self._stop.is_set() and cap is not None:
            ok, frame = cap.read()
            if not ok or frame is None:
                failures += 1
                if failures > 50:
                    with self._cond:
                        self._error = "Camera stopped delivering frames (disconnected?)"
                        self._cond.notify_all()
                    return
                time.sleep(0.02)
                continue
            failures = 0
            with self._cond:
                self._frame = frame
                self._seq += 1
                self._cond.notify_all()

    def read(self, timeout: float = 2.0) -> np.ndarray | None:
        """Wait for a frame newer than the last one returned (mirrored if configured).

        Returns ``None`` if no new frame arrived within ``timeout``; raises CameraError if the
        camera failed (e.g. it was unplugged).
        """
        if self._cap is None:
            raise CameraError("Camera is not open")
        with self._cond:
            if not self._cond.wait_for(lambda: self._seq != self._read_seq or self._error, timeout):
                return None
            if self._error:
                raise CameraError(self._error)
            frame = self._frame
            self._read_seq = self._seq
        if self.mirror:
            frame = cv2.flip(frame, 1)  # new array: the grabber can safely overwrite its slot
        return frame

    def release(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap is not None:
            try:
                self._cap.release()
            finally:
                self._cap = None
                log.info("Camera %s released", self.device)


_probe_lock = threading.Lock()


def probe_cameras(max_index: int = 5, skip: set[int] | None = None) -> list[dict]:
    """Return a list of available camera indices with their default resolution.

    Indices in ``skip`` (e.g. the camera currently used for tracking) are reported as available
    without opening them again.
    """
    found = []
    skip = skip or set()
    with _probe_lock:
        for index in range(max_index):
            if index in skip:
                found.append({"index": index, "label": f"Camera {index} (in use)"})
                continue
            backend = _backends()[0]
            cap = cv2.VideoCapture(index, backend)
            try:
                if cap.isOpened():
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        h, w = frame.shape[:2]
                        found.append({"index": index, "label": f"Camera {index} ({w}x{h})"})
            finally:
                cap.release()
    return found
