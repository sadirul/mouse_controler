"""Scroll execution.

The state machine produces fractional wheel notches. This controller caps bursts (so a jerky
hand cannot fling a page thousands of lines), and forwards the amount to the mouse backend,
which on Windows sends high-resolution wheel deltas for smooth scrolling.
"""
from __future__ import annotations

from app.mouse_controller import MouseController


class ScrollController:
    def __init__(self, mouse: MouseController, max_notches_per_event: float = 6.0, invert: bool = False):
        self.mouse = mouse
        self.max_notches = max_notches_per_event
        self.invert = invert
        self.total_v = 0.0
        self.total_h = 0.0

    def clamp(self, value: float) -> float:
        return max(-self.max_notches, min(self.max_notches, value))

    def scroll(self, dy: float, dx: float = 0.0) -> tuple[float, float]:
        """Scroll by ``dy`` (positive = up) and ``dx`` (positive = right) notches.

        Returns the amounts actually sent.
        """
        dy = self.clamp(dy)
        dx = self.clamp(dx)
        if self.invert:
            dy, dx = -dy, -dx
        if dy or dx:
            self.mouse.scroll(vertical=dy, horizontal=dx)
            self.total_v += dy
            self.total_h += dx
        return dy, dx
