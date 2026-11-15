"""Fingertip -> screen coordinate mapping with smoothing.

* The active camera region (configurable margins) is mapped onto the target screen area, so the
  user does not need to reach the edges of the camera frame to reach the edges of the screen.
* A One Euro filter removes jitter when the hand is still while keeping latency low on fast moves.
* A dead zone suppresses sub-pixel noise; "precision" damping slows the cursor while a pinch is
  being formed so clicks land where the user aimed.
* While pinching/dragging, motion is taken relative to the index knuckle (which does not move when
  the finger closes) instead of the fingertip.

This module does no OS calls; it only computes coordinates.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width - 1

    @property
    def bottom(self) -> int:
        return self.top + self.height - 1

    def clamp(self, x: float, y: float) -> tuple[float, float]:
        return min(max(x, self.left), self.right), min(max(y, self.top), self.bottom)


class _LowPass:
    def __init__(self) -> None:
        self.y: float | None = None

    def __call__(self, x: float, alpha: float) -> float:
        self.y = x if self.y is None else alpha * x + (1 - alpha) * self.y
        return self.y


class OneEuroFilter:
    """Casiez et al. 2012 - adaptive low-pass filter for noisy interactive signals."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.01, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self._x = _LowPass()
        self._dx = _LowPass()
        self._t: float | None = None
        self._prev: float | None = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x: float, t: float) -> float:
        if self._t is None or t <= self._t:
            self._t = t
            self._prev = x
            return self._x(x, 1.0)
        dt = t - self._t
        self._t = t
        dx = (x - self._prev) / dt
        self._prev = x
        edx = self._dx(dx, self._alpha(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(edx)
        return self._x(x, self._alpha(cutoff, dt))


class CursorController:
    def __init__(self, screen: Rect, cursor_cfg: dict[str, Any] | None = None):
        self.screen = screen
        self.configure(cursor_cfg or {})
        self.reset()

    def configure(self, cfg: dict[str, Any]) -> None:
        self.mode = cfg.get("mode", "absolute")
        self.speed = float(cfg.get("speed", 1.0))
        smoothing = float(cfg.get("smoothing", 0.55))
        responsiveness = float(cfg.get("responsiveness", 0.5))
        self.acceleration = float(cfg.get("acceleration", 0.6))
        self.dead_zone = float(cfg.get("dead_zone_px", 2))
        self.pinch_damping = float(cfg.get("pinch_damping", 0.35))
        region = cfg.get("region", {})
        self.region = (
            float(region.get("left", 0.15)),
            float(region.get("top", 0.12)),
            float(region.get("right", 0.85)),
            float(region.get("bottom", 0.72)),
        )
        if self.region[2] - self.region[0] < 0.1 or self.region[3] - self.region[1] < 0.1:
            self.region = (0.15, 0.12, 0.85, 0.72)
        # smoothing 0 -> min_cutoff 6 Hz (almost raw); 1 -> 0.25 Hz (very smooth)
        min_cutoff = 6.0 * (0.25 / 6.0) ** smoothing
        beta = 0.0003 + 0.012 * responsiveness  # pixel units: fast motion lifts the cutoff
        self._fx = OneEuroFilter(min_cutoff, beta)
        self._fy = OneEuroFilter(min_cutoff, beta)

    def set_screen(self, screen: Rect) -> None:
        self.screen = screen
        self.reset()

    def reset(self) -> None:
        self._fx.reset()
        self._fy.reset()
        self.position: tuple[int, int] | None = None
        self._target: tuple[float, float] | None = None
        self._last_raw: np.ndarray | None = None
        self._anchor0: np.ndarray | None = None
        self._anchor_cursor: tuple[float, float] | None = None
        self._last_t: float | None = None

    # ------------------------------------------------------------------ mapping helpers
    def effective_region(self) -> tuple[float, float, float, float]:
        """Camera region (normalised) that maps to the full screen, shrunk by ``speed``."""
        x0, y0, x1, y1 = self.region
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        hw, hh = (x1 - x0) / 2 / self.speed, (y1 - y0) / 2 / self.speed
        return cx - hw, cy - hh, cx + hw, cy + hh

    def map_point(self, nx: float, ny: float) -> tuple[float, float]:
        x0, y0, x1, y1 = self.effective_region()
        u = min(max((nx - x0) / (x1 - x0), 0.0), 1.0)
        v = min(max((ny - y0) / (y1 - y0), 0.0), 1.0)
        return self.screen.left + u * (self.screen.width - 1), self.screen.top + v * (self.screen.height - 1)

    def gain(self) -> tuple[float, float]:
        """Screen pixels per normalised camera unit."""
        x0, y0, x1, y1 = self.effective_region()
        return self.screen.width / (x1 - x0), self.screen.height / (y1 - y0)

    # ------------------------------------------------------------------ updates
    def _emit(self, x: float, y: float, t: float) -> tuple[int, int] | None:
        sx = self._fx(x, t)
        sy = self._fy(y, t)
        sx, sy = self.screen.clamp(sx, sy)
        self._target = (sx, sy)
        new = (int(round(sx)), int(round(sy)))
        if self.position is not None:
            if math.hypot(new[0] - self.position[0], new[1] - self.position[1]) < self.dead_zone:
                return None
        self.position = new
        return new

    def track(self, point: np.ndarray, t: float, precision: bool = False) -> tuple[int, int] | None:
        """Follow the index fingertip. Returns the new cursor position or None (no change)."""
        self._anchor0 = None
        point = np.asarray(point, dtype=float)
        if self.mode == "relative":
            return self._track_relative(point, t, precision)
        tx, ty = self.map_point(point[0], point[1])
        if precision and self._target is not None:
            k = self.pinch_damping
            tx = self._target[0] + (tx - self._target[0]) * k
            ty = self._target[1] + (ty - self._target[1]) * k
        self._last_raw = point
        return self._emit(tx, ty, t)

    def _track_relative(self, point: np.ndarray, t: float, precision: bool) -> tuple[int, int] | None:
        if self._last_raw is None or self._target is None or self._last_t is None:
            self._last_raw = point
            self._last_t = t
            if self._target is None:
                cx = self.screen.left + self.screen.width / 2
                cy = self.screen.top + self.screen.height / 2
                self._target = (cx, cy) if self.position is None else self.position
            return None
        dt = max(t - self._last_t, 1e-3)
        delta = point - self._last_raw
        self._last_raw = point
        self._last_t = t
        gx, gy = self.gain()
        speed = float(np.linalg.norm(delta)) / dt  # normalised units per second
        factor = 0.6 * (1.0 + self.acceleration * min(speed / 0.5, 4.0))
        if precision:
            factor *= self.pinch_damping
        tx = self._target[0] + delta[0] * gx * factor
        ty = self._target[1] + delta[1] * gy * factor
        tx, ty = self.screen.clamp(tx, ty)
        return self._emit(tx, ty, t)

    def anchor(self, anchor: np.ndarray, t: float) -> tuple[int, int] | None:
        """Move relative to where the pinch started (used while dragging)."""
        anchor = np.asarray(anchor, dtype=float)
        if self._anchor0 is None:
            self._anchor0 = anchor.copy()
            start = self.position if self.position is not None else self._target
            if start is None:
                self._anchor0 = None  # unknown cursor position - caller should sync() first
                return None
            self._anchor_cursor = (float(start[0]), float(start[1]))
            return None
        gx, gy = self.gain()
        dx, dy = (anchor - self._anchor0)[:2]
        tx = self._anchor_cursor[0] + dx * gx
        ty = self._anchor_cursor[1] + dy * gy
        self._last_raw = None
        return self._emit(tx, ty, t)

    def freeze(self) -> None:
        """Hold the cursor still. Relative state is reset so tracking resumes without a jump."""
        self._anchor0 = None
        self._last_raw = None
        self._last_t = None

    def sync(self, x: int, y: int) -> None:
        """Inform the controller of the real cursor position (e.g. moved by the physical mouse)."""
        self.position = (x, y)
        self._target = (float(x), float(y))
