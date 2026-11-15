"""Dark theme (Qt style sheet + palette)."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

ACCENT = "#7c6cff"
ACCENT_2 = "#22d3ee"
BG = "#0f1117"
SURFACE = "#171a23"
SURFACE_2 = "#1e2230"
BORDER = "#2a2f3f"
TEXT = "#e6e8ef"
MUTED = "#8b90a3"
OK = "#34d399"
WARN = "#fbbf24"
DANGER = "#f43f5e"

STYLE = f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QWidget#Root {{ background: {BG}; }}
QWidget#Sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #151827, stop:1 #10121a);
    border-right: 1px solid {BORDER};
}}
QLabel#AppName {{ font-size: 13pt; font-weight: 700; }}
QLabel#AppTag {{ color: {MUTED}; font-size: 8.5pt; }}
QPushButton#Nav {{
    text-align: left; padding: 10px 14px; border: none; border-radius: 10px;
    background: transparent; color: {MUTED}; font-weight: 600;
}}
QPushButton#Nav:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#Nav:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(124,108,255,0.28), stop:1 rgba(34,211,238,0.10));
    color: {TEXT}; border-left: 3px solid {ACCENT};
}}
QLabel#PageTitle {{ font-size: 18pt; font-weight: 700; }}
QLabel#PageSubtitle {{ color: {MUTED}; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Small {{ color: {MUTED}; font-size: 8.5pt; }}
QLabel#CardTitle {{ font-size: 11pt; font-weight: 700; }}
QLabel#TileValue {{ font-size: 12.5pt; font-weight: 700; }}
QLabel#TileLabel {{ color: {MUTED}; font-size: 8.5pt; text-transform: uppercase; letter-spacing: 1px; }}
QFrame#Card {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SURFACE_2}, stop:1 {SURFACE});
    border: 1px solid {BORDER}; border-radius: 16px;
}}
QFrame#Tile {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#Banner {{ border-radius: 12px; }}
QLabel#Preview {{ background: #07080c; border-radius: 12px; color: {MUTED}; }}
QPushButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 8px 16px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: #555a6b; border-color: #232736; }}
QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 #5b8cff); border: none; color: white;
}}
QPushButton#Primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8f81ff, stop:1 #6f9bff); }}
QPushButton#Primary:disabled {{ background: #2b2f42; color: #6b7086; }}
QPushButton#Danger {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f43f5e, stop:1 #e11d48); border: none; color: white;
}}
QPushButton#Danger:hover {{ background: #fb5a75; }}
QPushButton#Warn {{ background: rgba(251,191,36,0.15); border: 1px solid rgba(251,191,36,0.6); color: {WARN}; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px 8px; min-height: 22px;
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {BORDER}; selection-background-color: {ACCENT}; }}
QSlider::groove:horizontal {{ height: 6px; background: {BORDER}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2}); border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: white; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; border: 2px solid {ACCENT};
}}
QSlider::sub-page:horizontal:disabled {{ background: #3a3f52; }}
QSlider::handle:horizontal:disabled {{ background: #8b90a3; border-color: #3a3f52; }}
QLabel:disabled {{ color: #5b6073; }}
QRadioButton::indicator, QCheckBox::indicator {{ width: 16px; height: 16px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3b4157; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QTableView {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; gridline-color: {BORDER};
    alternate-background-color: #1a1d28; selection-background-color: rgba(124,108,255,0.35);
}}
QHeaderView::section {{ background: {SURFACE_2}; border: none; border-bottom: 1px solid {BORDER}; padding: 6px; font-weight: 700; color: {MUTED}; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; border-radius: 6px; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; padding: 6px; border-radius: 8px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: rgba(124,108,255,0.35); }}
QMessageBox {{ background: {SURFACE}; }}
QProgressBar {{ background: {BORDER}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ border-radius: 4px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2}); }}
"""


def rgba(color: str, alpha: float) -> str:
    """CSS rgba() from '#rrggbb' (Qt reads 8-digit hex as #AARRGGBB, so never append alpha digits)."""
    c = color.lstrip("#")
    return f"rgba({int(c[0:2], 16)}, {int(c[2:4], 16)}, {int(c[4:6], 16)}, {alpha})"


def palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(BG))
    p.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_2))
    p.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    p.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Button, QColor(SURFACE_2))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE_2))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
    return p
