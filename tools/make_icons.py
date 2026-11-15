"""Render ui/assets/icon.svg to PNG and multi-size ICO (used by the app, tray and PyInstaller)."""
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication(sys.argv)
assets = ROOT / "ui" / "assets"
renderer = QSvgRenderer(str(assets / "icon.svg"))


def render(size: int) -> Image.Image:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p)
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


big = render(512)
big.resize((256, 256), Image.LANCZOS).save(assets / "icon.png")
big.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icons written to", assets)
