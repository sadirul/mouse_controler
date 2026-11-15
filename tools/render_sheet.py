"""Render every gesture illustration into one PNG contact sheet (visual check)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from ui.gesture_art import GESTURE_ART, gesture_svg

app = QGuiApplication(sys.argv)
keys = list(GESTURE_ART)
cols, cw, ch = 5, 240, 300
img = QImage(cols * cw, ((len(keys) + cols - 1) // cols) * ch, QImage.Format.Format_ARGB32)
img.fill(QColor("#0f1117"))
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
p.setPen(QColor("#e6e8ef"))
p.setFont(QFont("Segoe UI", 11))
for i, k in enumerate(keys):
    x, y = (i % cols) * cw, (i // cols) * ch
    QSvgRenderer(QByteArray(gesture_svg(k).encode())).render(p, QRectF(x + 10, y + 10, 220, 243))
    p.drawText(QRectF(x, y + 265, cw, 24), Qt.AlignmentFlag.AlignCenter, k)
p.end()
out = sys.argv[1] if len(sys.argv) > 1 else "sheet.png"
img.save(out)
print(out)
