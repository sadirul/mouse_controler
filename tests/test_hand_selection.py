"""Which hand controls the mouse (left, right or either)."""
from __future__ import annotations

import numpy as np

from app.hand_tracker import TrackedHand, select_hand


def _hand(side: str, score: float) -> TrackedHand:
    return TrackedHand(np.zeros((21, 3)), side, score)


def test_either_hand_accepts_left_and_right():
    assert select_hand([_hand("Left", 0.9)], "any").handedness == "Left"
    assert select_hand([_hand("Right", 0.9)], "any").handedness == "Right"


def test_either_hand_keeps_current_hand_when_both_visible():
    hands = [_hand("Right", 0.95), _hand("Left", 0.80)]
    # No hand in control yet: the most confident hand wins.
    assert select_hand(hands, "any").handedness == "Right"
    # The left hand is in control: it keeps control even though the right hand scores higher.
    assert select_hand(hands, "any", previous="Left").handedness == "Left"


def test_either_hand_falls_back_when_current_hand_leaves():
    assert select_hand([_hand("Right", 0.9)], "any", previous="Left").handedness == "Right"


def test_fixed_hand_ignores_the_other_hand():
    hands = [_hand("Left", 0.99)]
    assert select_hand(hands, "right") is None
    assert select_hand(hands, "left", previous="Right").handedness == "Left"


def test_min_score_applies_to_either_hand():
    assert select_hand([_hand("Left", 0.4)], "any", min_score=0.6) is None
