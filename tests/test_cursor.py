"""Cursor mapping, smoothing, dead zone and relative/anchor motion."""
from __future__ import annotations

import numpy as np
import pytest

from app.cursor_controller import CursorController, OneEuroFilter, Rect
from app.mouse_controller import MouseController
from tests.conftest import FakeMouseBackend

SCREEN = Rect(0, 0, 1920, 1080)


def make(**cfg) -> CursorController:
    base = {"smoothing": 0.0, "dead_zone_px": 0}
    base.update(cfg)
    return CursorController(SCREEN, base)


def settle(c: CursorController, point, t0=0.0, frames=60):
    pos = None
    t = t0
    for _ in range(frames):
        t += 1 / 30
        p = c.track(np.array(point), t)
        pos = p or pos
    return c.position, t


def test_region_maps_to_screen_corners():
    c = make()
    assert c.map_point(0.15, 0.12) == (0, 0)
    assert c.map_point(0.85, 0.72) == (1919, 1079)
    x, y = c.map_point(0.5, 0.42)
    assert x == pytest.approx(959.5) and y == pytest.approx(539.5)


def test_points_outside_region_are_clamped():
    c = make()
    assert c.map_point(-1, -1) == (0, 0)
    assert c.map_point(2, 2) == (1919, 1079)


def test_speed_shrinks_region():
    slow, fast = make(speed=1.0), make(speed=2.0)
    assert fast.map_point(0.6, 0.42)[0] > slow.map_point(0.6, 0.42)[0]
    assert fast.map_point(0.5, 0.42) == pytest.approx(slow.map_point(0.5, 0.42))


def test_multi_monitor_negative_coordinates():
    c = CursorController(Rect(-1920, 0, 3840, 1080), {"smoothing": 0})
    assert c.map_point(0.15, 0.12)[0] == -1920
    pos, _ = settle(c, (0.15, 0.3))
    assert pos[0] == -1920


def test_tracking_converges_to_target():
    c = make(smoothing=0.5)
    pos, _ = settle(c, (0.5, 0.42))
    assert abs(pos[0] - 960) <= 2 and abs(pos[1] - 540) <= 2


def test_smoothing_reduces_jitter(rng):
    def jitter(smoothing):
        c = make(smoothing=smoothing)
        xs = []
        t = 0.0
        for i in range(120):
            t += 1 / 30
            c.track(np.array([0.5, 0.42]) + rng.normal(0, 0.002, 2), t)
            if i > 30:
                xs.append(c.position[0])
        return np.std(xs)

    assert jitter(0.8) < jitter(0.0) * 0.5


def test_dead_zone_suppresses_small_moves():
    c = make(dead_zone_px=10)
    settle(c, (0.5, 0.42))
    t = 10.0
    assert c.track(np.array([0.5005, 0.42]), t) is None


def test_one_euro_follows_fast_motion():
    f = OneEuroFilter(min_cutoff=0.5, beta=0.05)
    t = 0.0
    out = 0.0
    for i in range(30):
        t += 1 / 30
        out = f(i * 50.0, t)
    assert out > 29 * 50.0 * 0.8


def test_precision_damping_slows_cursor():
    normal, precise = make(), make(pinch_damping=0.2)
    for c in (normal, precise):
        settle(c, (0.5, 0.42))
    t = 20.0
    a = normal.track(np.array([0.6, 0.42]), t)
    b = precise.track(np.array([0.6, 0.42]), t, precision=True)
    assert (b[0] - 960) < (a[0] - 960) * 0.5


def test_anchor_moves_relative_to_start():
    c = make()
    pos, t = settle(c, (0.5, 0.42))
    assert c.anchor(np.array([0.3, 0.3]), t + 0.03) is None  # first call records the anchor
    new = None
    for i in range(30):
        t += 1 / 30
        new = c.anchor(np.array([0.37, 0.3]), t + 0.03) or new
    gx, _ = c.gain()
    assert c.position[0] == pytest.approx(pos[0] + 0.07 * gx, abs=3)


def test_relative_mode_with_acceleration():
    def travel(accel, step):
        c = make(mode="relative", acceleration=accel)
        c.sync(960, 540)
        t = 0.0
        p = np.array([0.5, 0.42])
        for _ in range(10):
            t += 1 / 30
            p = p + np.array([step, 0])
            c.track(p, t)
        return c.position[0] - 960

    assert travel(0.0, 0.01) > 0
    assert travel(2.0, 0.01) > travel(0.0, 0.01)


def test_mouse_controller_tracks_held_buttons():
    backend = FakeMouseBackend()
    m = MouseController(backend)
    m.down("left")
    m.down("left")  # no duplicate press
    assert [c[0] for c in backend.calls] == ["down"]
    m.click("left")  # releases the held button before clicking
    assert m.held_buttons == set()
    m.down("right")
    m.release_all()
    assert backend.calls[-1][:2] == ("up", "right")
