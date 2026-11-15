"""Gesture settings: every supported gesture with illustration, description, action and options."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.settings_manager import SettingsManager
from ui import theme
from ui.binding import Binder
from ui.gesture_art import gesture_svg
from ui.widgets import Card, Row, SliderRow, ToggleSwitch, page_header, scroll_page

ms = lambda v: f"{v:.0f} ms"  # noqa: E731
hs = lambda v: f"{v:.2f} hand"  # noqa: E731
pct = lambda v: f"{v * 100:.1f}%"  # noqa: E731

WINDOW_ACTION_LABELS = [
    ("none", "Do nothing"),
    ("minimize", "Minimize window"),
    ("maximize", "Maximize window"),
    ("restore", "Restore window"),
    ("restore_or_minimize", "Restore (if maximized) / minimize"),
    ("maximize_toggle", "Toggle maximize / restore"),
    ("close", "Close window (needs confirmation)"),
    ("switch_app", "Switch application (Alt+Tab)"),
    ("snap_left", "Move window to left half"),
    ("snap_right", "Move window to right half"),
    ("move_top", "Move window to top of screen"),
]

# (key, title, art, description, action, enable path, controls)
# control: ("slider", label, path, min, max, step, fmt, cast) | ("combo", label, path, options) |
#          ("toggle", label, path, description) | ("mapping", label, trigger)
GESTURES = [
    ("move", "Move cursor", "move",
     "Extend your index finger and keep the other fingers folded or relaxed. Move the finger to move the cursor. "
     "Make a fist to hold the cursor still while you reposition your hand.",
     "Moves the mouse cursor", "gestures.move.enabled",
     [("slider", "Detection time", "gestures.move.min_ms", 0, 300, 10, ms, int)]),
    ("click", "Left click", "click",
     "Touch the tips of your thumb and index finger together, then release. Holding the pinch never repeats the click.",
     "Single left click", "gestures.click.enabled",
     [("slider", "Pinch threshold", "gestures.click.pinch_threshold", 0.1, 0.6, 0.01, hs, float),
      ("slider", "Release threshold", "gestures.click.release_threshold", 0.15, 0.8, 0.01, hs, float),
      ("slider", "Detection time", "gestures.click.min_ms", 0, 300, 10, ms, int),
      ("slider", "Cooldown", "gestures.click.cooldown_ms", 0, 1000, 10, ms, int)]),
    ("double_click", "Double click", "double_click",
     "Make two quick thumb + index pinches. The cursor stays still between the pinches so both land on the same spot.",
     "Double left click", "gestures.double_click.enabled",
     [("slider", "Max time between pinches", "gestures.double_click.interval_ms", 150, 800, 10, ms, int)]),
    ("right_click", "Right click", "right_click",
     "Touch the tips of your thumb and middle finger together.",
     "Single right click", "gestures.right_click.enabled",
     [("slider", "Pinch threshold", "gestures.right_click.pinch_threshold", 0.1, 0.6, 0.01, hs, float),
      ("slider", "Detection time", "gestures.right_click.min_ms", 0, 400, 10, ms, int),
      ("slider", "Cooldown", "gestures.right_click.cooldown_ms", 0, 2000, 50, ms, int)]),
    ("long_press", "Long press", "long_press",
     "Hold the thumb + index pinch without moving.",
     "Hold left button (or right click)", "gestures.long_press.enabled",
     [("slider", "Hold duration", "gestures.long_press.duration_ms", 300, 3000, 50, ms, int),
      ("combo", "Long press action", "gestures.long_press.mode",
       [("hold", "Press and hold the left button (drag activation)"), ("right_click", "Right click")])]),
    ("drag", "Drag and drop", "drag",
     "Pinch thumb + index on an item, keep pinching while you move your hand, release to drop. "
     "Works for files, icons, text selections, sliders and window title bars.",
     "Left button down, move, button up", "gestures.drag.enabled",
     [("toggle", "Start dragging when the pinch moves", "gestures.drag.on_move",
       "When off, dragging only starts after a long press."),
      ("slider", "Movement to start a drag", "gestures.drag.move_threshold", 0.005, 0.1, 0.005, pct, float)]),
    ("scroll_vertical", "Vertical scroll", "scroll_vertical",
     "Extend index and middle fingers held together (other fingers folded) and move them up or down.",
     "Scroll up / down", "gestures.scroll_vertical.enabled",
     [("slider", "Scroll speed", "gestures.scroll_vertical.speed", 5, 120, 1, lambda v: f"{v:.0f}", float),
      ("combo", "Scroll style", "gestures.scroll.mode",
       [("touchpad", "Touchpad - scroll follows finger movement"), ("joystick", "Joystick - distance sets scroll speed")]),
      ("slider", "Detection time", "gestures.scroll.min_ms", 0, 500, 10, ms, int),
      ("toggle", "Fingers must be held together", "gestures.scroll.require_together",
       "Prevents a spread 'V' sign from scrolling accidentally.")]),
    ("scroll_horizontal", "Horizontal scroll", "scroll_horizontal",
     "Same two-finger pose - move the hand left or right. The first clear direction locks the axis "
     "until you release the pose.",
     "Scroll left / right (where supported)", "gestures.scroll_horizontal.enabled",
     [("slider", "Scroll speed", "gestures.scroll_horizontal.speed", 5, 120, 1, lambda v: f"{v:.0f}", float)]),
    ("window_move", "Grab and move window", "window_move",
     "Hold up three fingers (index, middle, ring) to grab the window, move your hand to move it, change pose to release. "
     "Maximized windows are restored first; window size is preserved.",
     "Moves the window", "gestures.window_move.enabled",
     [("combo", "Gesture", "gestures.window_move.pose",
       [("index_middle_ring", "Index + middle + ring fingers"), ("thumb_index_middle", "Thumb + index + middle fingers")]),
      ("combo", "Move method", "gestures.window_move.mode",
       [("direct", "Direct (Windows API)"), ("titlebar", "Drag the title bar with the mouse")]),
      ("combo", "Window to move", "gestures.window_move.target",
       [("active", "Active (foreground) window"), ("under_cursor", "Window under the cursor")]),
      ("slider", "Movement gain", "gestures.window_move.gain", 0.5, 3.0, 0.1, lambda v: f"{v:.1f}x", float),
      ("slider", "Detection time", "gestures.window_move.min_ms", 50, 800, 10, ms, int)]),
    ("window_swipe", "Window swipes", "window_swipe",
     "Four fingers up with the thumb tucked in, then swipe quickly up, down, left or right.",
     "Configurable window commands", "gestures.window_swipe.enabled",
     [("mapping", "Swipe up", "four_swipe_up"), ("mapping", "Swipe down", "four_swipe_down"),
      ("mapping", "Swipe left", "four_swipe_left"), ("mapping", "Swipe right", "four_swipe_right"),
      ("slider", "Swipe distance", "gestures.window_swipe.distance", 0.4, 2.0, 0.05, hs, float),
      ("slider", "Max swipe time", "gestures.window_swipe.window_ms", 300, 1500, 50, ms, int),
      ("slider", "Cooldown", "gestures.window_swipe.cooldown_ms", 200, 3000, 50, ms, int)]),
    ("horns", "Horns hold", "horns",
     "Extend index and pinky fingers (middle and ring folded) and hold.",
     "Configurable (default: switch application)", "gestures.horns.enabled",
     [("mapping", "Action", "horns_hold"),
      ("slider", "Hold duration", "gestures.horns.hold_ms", 200, 2000, 50, ms, int),
      ("slider", "Cooldown", "gestures.horns.cooldown_ms", 200, 4000, 50, ms, int)]),
    ("thumb_pinky", "Thumb + pinky hold", "thumb_pinky",
     "Touch thumb and pinky tips and hold. Closing a window always needs confirmation: repeat the gesture "
     "within the confirmation window, or confirm in a dialog.",
     "Configurable (default: close window)", "gestures.thumb_pinky.enabled",
     [("mapping", "Action", "thumb_pinky_hold"),
      ("slider", "Hold duration", "gestures.thumb_pinky.hold_ms", 300, 2500, 50, ms, int),
      ("combo", "Close confirmation", "gestures.close_confirm.mode",
       [("gesture", "Repeat the gesture to confirm"), ("dialog", "Show a confirmation dialog")]),
      ("slider", "Confirmation window", "gestures.close_confirm.window_ms", 1500, 8000, 100, ms, int),
      ("slider", "Pinch threshold", "gestures.thumb_pinky.pinch_threshold", 0.1, 0.6, 0.01, hs, float)]),
    ("emergency_stop", "Emergency stop", "emergency_stop",
     "Show an open palm (all five fingers extended) to the camera and hold it. All mouse and window actions stop "
     "immediately and stay off until you press Resume. Has priority over every other gesture.",
     "Disables all gesture actions", "gestures.emergency_stop.enabled",
     [("slider", "Hold duration", "gestures.emergency_stop.hold_ms", 500, 4000, 50, ms, int),
      ("toggle", "Palm must face the camera", "gestures.emergency_stop.require_palm_facing",
       "Stricter, but may fail if the hand's left/right detection is uncertain.")]),
]


class GestureCard(Card):
    def __init__(self, spec, binder: Binder, settings: SettingsManager):
        key, title, art, desc, action, enable_path, controls = spec
        super().__init__()
        self.key = key
        top = QHBoxLayout()
        top.setSpacing(18)
        svg = QSvgWidget()
        svg.load(QByteArray(gesture_svg(art).encode()))
        svg.setFixedSize(118, 130)
        top.addWidget(svg, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(4)
        head = QHBoxLayout()
        name = QLabel(title)
        name.setObjectName("CardTitle")
        head.addWidget(name)
        head.addStretch()
        self.toggle = binder.toggle(ToggleSwitch(), enable_path)
        head.addWidget(QLabel("Enabled"))
        head.addWidget(self.toggle)
        text.addLayout(head)
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setObjectName("Muted")
        text.addWidget(d)
        a = QLabel(f"<span style='color:{theme.MUTED}'>Action:</span> <b style='color:{theme.ACCENT_2}'>{action}</b>")
        text.addWidget(a)
        top.addLayout(text, 1)
        self.add_layout(top)

        self.controls = QWidget()
        lay = QVBoxLayout(self.controls)
        lay.setContentsMargins(136, 4, 0, 0)
        lay.setSpacing(6)
        for c in controls:
            kind = c[0]
            if kind == "slider":
                _, label, path, lo, hi, step, fmt, cast = c
                lay.addWidget(binder.slider(SliderRow(label, lo, hi, settings.get(path), step, fmt), path, cast))
            elif kind == "combo":
                _, label, path, options = c
                lay.addWidget(Row(label, binder.combo(QComboBox(), path, options)))
            elif kind == "toggle":
                _, label, path, help_text = c
                lay.addWidget(Row(label, binder.toggle(ToggleSwitch(), path), help_text))
            elif kind == "mapping":
                _, label, trigger = c
                combo = binder.combo(QComboBox(), f"gestures.mappings.{trigger}", WINDOW_ACTION_LABELS)
                combo.setMinimumWidth(280)
                lay.addWidget(Row(label, combo))
        self.add(self.controls)
        self.toggle.toggled.connect(self._enabled_changed)
        self._enabled_changed(self.toggle.isChecked())

    def _enabled_changed(self, on: bool) -> None:
        self.controls.setEnabled(on)


class GestureSettingsPage(QWidget):
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.binder = Binder(settings, self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        head = QHBoxLayout()
        head.addWidget(page_header(
            "Gestures",
            "Every gesture can be enabled or disabled and tuned. Changes apply immediately and are saved "
            "to gestures.json. Pinch distances are measured in hand sizes, so they work at any distance."), 1)
        reset = QPushButton("Reset gestures to defaults")
        reset.clicked.connect(self._reset)
        head.addWidget(reset, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)
        self.cards = [GestureCard(spec, self.binder, settings) for spec in GESTURES]
        for card in self.cards:
            lay.addWidget(card)
        lay.addStretch()
        outer.addWidget(scroll_page(content))

    def _reset(self) -> None:
        self.settings.reset("gestures")
        self.binder.refresh_all()
