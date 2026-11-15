"""Parametric SVG hand illustrations for every gesture.

The same geometry is used by the documentation site's animated hands (docs/js/gesture-demo.js),
so the GUI and the docs show identical poses.
"""
from __future__ import annotations

from functools import lru_cache

# finger: (knuckle x, width, length, default angle)
FINGERS = {
    "index": (66, 21, 74, -6),
    "middle": (90, 22, 84, -1),
    "ring": (113, 21, 78, 4),
    "pinky": (135, 18, 60, 10),
}
THUMB = (58, 160, 23, 72)  # base x, base y, width, length
KNUCKLE_Y = 126

FOLD = 0.36
TUCK = (38, 0.72)  # thumb folded across the palm

# pose: finger -> (angle, length scale); "thumb" -> (angle, scale)
POSES: dict[str, dict[str, tuple[float, float]]] = {
    "open": {"index": (-6, 1), "middle": (-1, 1), "ring": (4, 1), "pinky": (10, 1), "thumb": (-42, 1)},
    "point": {"index": (-6, 1), "middle": (-1, FOLD), "ring": (4, FOLD), "pinky": (10, FOLD), "thumb": TUCK},
    "pinch_index": {"index": (-40, 0.62), "middle": (-1, FOLD), "ring": (4, FOLD), "pinky": (10, FOLD), "thumb": (-17.3, 1.0)},
    "pinch_middle": {"index": (-30, 1), "middle": (-45, 0.55), "ring": (4, FOLD), "pinky": (10, FOLD), "thumb": (-0.6, 0.93)},
    "pinch_pinky": {"index": (-6, FOLD), "middle": (-1, FOLD), "ring": (4, FOLD), "pinky": (-40, 0.5), "thumb": (45.3, 1.13)},
    "two": {"index": (-3, 1), "middle": (-1, 1), "ring": (4, FOLD), "pinky": (10, FOLD), "thumb": TUCK},
    "three": {"index": (-4, 1), "middle": (-1, 1), "ring": (3, 1), "pinky": (10, FOLD), "thumb": TUCK},
    "four": {"index": (-6, 1), "middle": (-1, 1), "ring": (4, 1), "pinky": (10, 1), "thumb": TUCK},
    "horns": {"index": (-8, 1), "middle": (-1, FOLD), "ring": (4, FOLD), "pinky": (12, 1), "thumb": TUCK},
    "fist": {"index": (-6, FOLD), "middle": (-1, FOLD), "ring": (4, FOLD), "pinky": (10, FOLD), "thumb": TUCK},
}

SKIN = "#dfe3ee"
SKIN_EDGE = "#a3abc2"
ACTIVE_A = "#8b7dff"
ACTIVE_B = "#38d5f0"
CYAN = "#22d3ee"
ORANGE = "#fb923c"
ARROW = "#fbbf24"

_DEFS = f"""<defs>
<linearGradient id="act" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{ACTIVE_B}"/><stop offset="1" stop-color="{ACTIVE_A}"/></linearGradient>
<linearGradient id="skin" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#eef1f8"/><stop offset="1" stop-color="{SKIN}"/></linearGradient>
<linearGradient id="curl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e9ecf4"/><stop offset="1" stop-color="#c9cfdd"/></linearGradient>
<marker id="ah" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{ARROW}"/></marker>
</defs>"""


def _finger(name: str, angle: float, scale: float, active: bool) -> str:
    bx, w, length, _ = FINGERS[name]
    fill = "url(#act)" if active else "url(#skin)"
    if scale <= FOLD + 0.01:
        # Curled finger seen from the front: a knuckle bump folded over the top of the palm.
        return (f'<g transform="translate({bx} {KNUCKLE_Y})">'
                f'<rect x="{-w / 2}" y="-20" width="{w}" height="44" rx="{w / 2}" fill="url(#curl)" stroke="{SKIN_EDGE}" stroke-width="1.5"/>'
                f'<line x1="{-w / 2 + 4}" x2="{w / 2 - 4}" y1="2" y2="2" stroke="{SKIN_EDGE}" stroke-width="1.2"/></g>')
    h = length * scale
    parts = [f'<g transform="translate({bx} {KNUCKLE_Y}) rotate({angle})">',
             f'<rect x="{-w / 2}" y="{-h:.1f}" width="{w}" height="{h + 18:.1f}" rx="{w / 2}" fill="{fill}" stroke="{SKIN_EDGE}" stroke-width="1.5"/>',
             f'<rect x="{-w / 2 + 5}" y="{-h + 4:.1f}" width="{w - 10}" height="9" rx="4" fill="#ffffff" opacity="0.55"/>',
             f'<line x1="{-w / 2 + 4}" x2="{w / 2 - 4}" y1="{-h * 0.45:.1f}" y2="{-h * 0.45:.1f}" stroke="{SKIN_EDGE}" stroke-width="1" opacity="0.6"/>',
             "</g>"]
    return "".join(parts)


def _tip(name: str, angle: float, scale: float) -> tuple[float, float]:
    import math

    if name == "thumb":
        bx, by, _w, length = THUMB
    else:
        bx, _w, length, _ = FINGERS[name]
        by = KNUCKLE_Y
    h = length * scale - 4
    a = math.radians(angle)
    return bx + h * math.sin(a), by - h * math.cos(a)


def _thumb(angle: float, scale: float, active: bool) -> str:
    bx, by, w, length = THUMB
    h = length * scale
    fill = "url(#act)" if active else "url(#skin)"
    return (f'<g transform="translate({bx} {by}) rotate({angle})">'
            f'<rect x="{-w / 2}" y="{-h:.1f}" width="{w}" height="{h + 22:.1f}" rx="{w / 2}" fill="{fill}" stroke="{SKIN_EDGE}" stroke-width="1.5"/>'
            f'<rect x="{-w / 2 + 5}" y="{-h + 4:.1f}" width="{w - 10}" height="9" rx="4" fill="#ffffff" opacity="0.55"/></g>')


def hand(pose: str, active: tuple[str, ...] = (), markers: tuple[str, ...] = ("index", "thumb")) -> str:
    """SVG fragment (no <svg> wrapper) of a hand in ``pose``.

    Layering: thumb (when it sticks out sideways) -> extended fingers -> palm -> curled fingers
    -> thumb (when it crosses in front: tucked or pinching) -> fingers bending into a pinch
    -> fingertip markers.
    """
    p = POSES[pose]
    thumb_front = p["thumb"][0] > -20
    order = ("pinky", "ring", "middle", "index")
    curled = [n for n in order if p[n][1] <= FOLD + 0.01]
    bending = [n for n in order if FOLD + 0.01 < p[n][1] < 0.9]  # meeting the thumb in a pinch
    straight = [n for n in order if n not in curled and n not in bending]
    out = ['<rect x="72" y="196" width="58" height="46" rx="14" fill="url(#skin)" stroke="#a3abc2" stroke-width="1.5"/>']
    if not thumb_front:
        out.append(_thumb(*p["thumb"], "thumb" in active))
    for name in straight:
        out.append(_finger(name, *p[name], name in active))
    out.append('<rect x="50" y="116" width="100" height="96" rx="30" fill="url(#skin)" stroke="#a3abc2" stroke-width="1.5"/>')
    for name in curled:
        out.append(_finger(name, *p[name], name in active))
    if thumb_front:
        out.append(_thumb(*p["thumb"], "thumb" in active))
    for name in bending:
        out.append(_finger(name, *p[name], name in active))
    for m in markers:
        x, y = _tip(m, *p[m])
        color = CYAN if m == "index" else ORANGE
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}" stroke="#0f1117" stroke-width="1.5"/>')
    return "".join(out)


def _arrow(x1, y1, x2, y2) -> str:
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{ARROW}" stroke-width="5" '
            f'stroke-linecap="round" marker-end="url(#ah)"/>')


def _cross(cx: float = 172, cy: float = 40, r: float = 26) -> str:
    """Four-way arrows icon (cursor movement / swipe directions)."""
    a = 9
    return (_arrow(cx, cy - a, cx, cy - r) + _arrow(cx, cy + a, cx, cy + r)
            + _arrow(cx - a, cy, cx - r, cy) + _arrow(cx + a, cy, cx + r, cy))


def _badge(text: str, x: float = 168, y: float = 30) -> str:
    half = max(24, 6 + 4.6 * len(text))
    return (f'<g><rect x="{x - half}" y="{y - 15}" width="{2 * half}" height="28" rx="14" fill="#1e2230" stroke="{ARROW}" stroke-width="2"/>'
            f'<text x="{x}" y="{y + 5}" font-family="Segoe UI, sans-serif" font-size="14" font-weight="700" fill="{ARROW}" text-anchor="middle">{text}</text></g>')


GESTURE_ART = {
    "move": ("point", ("index",), lambda: _cross()),
    "click": ("pinch_index", ("index", "thumb"), lambda: _badge("x1")),
    "double_click": ("pinch_index", ("index", "thumb"), lambda: _badge("x2")),
    "right_click": ("pinch_middle", ("middle", "thumb"), lambda: _badge("R")),
    "long_press": ("pinch_index", ("index", "thumb"), lambda: f'<circle cx="168" cy="34" r="20" fill="none" stroke="#2a2f3f" stroke-width="5"/><path d="M168 14 A20 20 0 1 1 148 34" fill="none" stroke="{ARROW}" stroke-width="5" stroke-linecap="round"/>'),
    "drag": ("pinch_index", ("index", "thumb"), lambda: f'<rect x="150" y="20" width="34" height="40" rx="5" fill="#1e2230" stroke="{CYAN}" stroke-width="2.5"/>' + _arrow(118, 70, 150, 70)),
    "scroll_vertical": ("two", ("index", "middle"), lambda: _arrow(170, 80, 170, 20) + _arrow(170, 110, 170, 170)),
    "scroll_horizontal": ("two", ("index", "middle"), lambda: _arrow(176, 40, 206, 40) + _arrow(164, 40, 134, 40)),
    "window_move": ("three", ("index", "middle", "ring"), lambda: f'<rect x="150" y="14" width="46" height="34" rx="5" fill="#1e2230" stroke="{CYAN}" stroke-width="2.5"/><line x1="150" y1="23" x2="196" y2="23" stroke="{CYAN}" stroke-width="2"/>' + _arrow(160, 62, 190, 80)),
    "window_swipe": ("four", ("index", "middle", "ring", "pinky"), lambda: f'<rect x="160" y="30" width="24" height="20" rx="3" fill="#1e2230" stroke="{CYAN}" stroke-width="2"/>' + _cross(172, 40, 34)),
    "horns": ("horns", ("index", "pinky"), lambda: _badge("Alt+Tab", 172, 20)),
    "thumb_pinky": ("pinch_pinky", ("pinky", "thumb"), lambda: _badge("x2", 170)),
    "emergency_stop": ("open", ("thumb", "index", "middle", "ring", "pinky"), lambda: '<circle cx="100" cy="120" r="112" fill="none" stroke="#f43f5e" stroke-width="5" stroke-dasharray="14 8"/>'),
    "fist": ("fist", (), lambda: ""),
}


@lru_cache(maxsize=None)
def gesture_svg(key: str, size: int = 220) -> str:
    pose, active, extra = GESTURE_ART[key]
    markers = tuple(m for m in ("index", "thumb") if m in active)
    if key == "right_click":
        markers = ("thumb",)
    if key == "thumb_pinky":
        markers = ("thumb",)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-14 -8 228 252" width="{size}" height="{size * 252 // 228}">'
            f"{_DEFS}{hand(pose, active, markers)}{extra()}</svg>")


def export_all(directory) -> list[str]:
    from pathlib import Path

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for key in GESTURE_ART:
        path = directory / f"{key}.svg"
        path.write_text(gesture_svg(key), encoding="utf-8")
        written.append(str(path))
    return written
