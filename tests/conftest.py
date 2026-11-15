"""Shared fixtures. OS-level mouse/window actions are always replaced by recording fakes."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cursor_controller import Rect  # noqa: E402
from app.gesture_controller import GestureController  # noqa: E402
from app.hand_tracker import TrackedHand  # noqa: E402
from app.logger import ActivityLog  # noqa: E402
from app.mouse_controller import MouseController  # noqa: E402
from app.settings_manager import DEFAULT_GESTURES, DEFAULT_SETTINGS  # noqa: E402
from app.simulation import pose_landmarks  # noqa: E402
from app.window_controller import WindowInfo  # noqa: E402

FPS = 30.0
DT = 1.0 / FPS


class FakeMouseBackend:
    """Records every OS mouse call instead of performing it."""

    def __init__(self) -> None:
        self.pos = (500, 500)
        self.calls: list[tuple] = []

    def move(self, x: int, y: int) -> None:
        self.pos = (x, y)
        self.calls.append(("move", x, y))

    def position(self) -> tuple[int, int]:
        return self.pos

    def button(self, button: str, down: bool) -> None:
        self.calls.append(("down" if down else "up", button, self.pos))

    def wheel(self, vertical: float, horizontal: float) -> None:
        self.calls.append(("wheel", vertical, horizontal))

    # helpers --------------------------------------------------------------------------
    def of(self, kind: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == kind]

    def clicks(self, button: str = "left") -> int:
        return len([c for c in self.calls if c[0] == "up" and c[1] == button])


class FakeWindows:
    supported = True

    def __init__(self) -> None:
        self.own_pid = 1
        self.calls: list[tuple] = []
        self._grab = False

    def _info(self) -> WindowInfo:
        return WindowInfo(42, "Notepad", "Notepad", 100, 100, 800, 600, False, 999)

    def target(self, mode: str = "active") -> WindowInfo:
        return self._info()

    def begin_move(self, mode: str = "active") -> WindowInfo:
        self._grab = True
        self.calls.append(("begin",))
        return self._info()

    def move_by(self, dx: int, dy: int) -> None:
        self.calls.append(("move_by", dx, dy))

    def end_move(self):
        was = self._grab
        self._grab = False
        self.calls.append(("end",))
        return self._info() if was else None

    @property
    def grabbing(self) -> bool:
        return self._grab

    def title_bar_point(self, info):
        return (500, 110)

    def command(self, action: str, mode: str = "active") -> str:
        self.calls.append(("command", action))
        return action


def default_config() -> dict:
    cfg = copy.deepcopy(DEFAULT_SETTINGS)
    cfg.update(copy.deepcopy(DEFAULT_GESTURES))
    return cfg


class Sim:
    """Drives a full GestureController with synthetic hands at 30 FPS."""

    def __init__(self, config: dict | None = None):
        self.config = config or default_config()
        self.backend = FakeMouseBackend()
        self.mouse = MouseController(self.backend)
        self.windows = FakeWindows()
        self.activity = ActivityLog()
        self.notices: list[tuple[str, dict]] = []
        self.controller = GestureController(
            self.config, self.mouse, self.windows, self.activity, Rect(0, 0, 1920, 1080),
            notify=lambda k, d: self.notices.append((k, d)),
        )
        self.t = 100.0
        self.results = []

    def hold(self, pose: str | None, ms: float, move: tuple[float, float] = (0.0, 0.0),
             start: tuple[float, float] = (0.5, 0.75), **overrides):
        """Show ``pose`` for ``ms`` milliseconds, moving the wrist linearly by ``move``."""
        frames = max(1, int(round(ms / 1000.0 * FPS)))
        out = []
        for i in range(frames):
            frac = (i + 1) / frames
            center = (start[0] + move[0] * frac, start[1] + move[1] * frac)
            hand = None
            if pose is not None:
                lm = pose_landmarks(pose, center=center, **overrides)
                hand = TrackedHand(lm, overrides.get("hand", "Right"), 0.95)
            self.t += DT
            r = self.controller.process(hand, self.t)
            out.append(r)
            self.results.append(r)
        return out

    def events(self) -> list[str]:
        return [e.kind for r in self.results for e in r.decision.events]


@pytest.fixture
def sim():
    return Sim()


@pytest.fixture
def config():
    return default_config()


def features_for(pose: str, **kw):
    from app.gesture_detector import extract_features

    hand = kw.pop("hand", "Right")
    return extract_features(pose_landmarks(pose, hand=hand, **kw), handedness=hand)


@pytest.fixture
def rng():
    return np.random.default_rng(0)
