"""Render the documentation page with Chromium (Qt WebEngine) for visual checks.

    python tools/render_docs.py OUTDIR [width] [theme]
Writes top.png plus demo-<name>-<pct>.png with animations frozen at several moments.
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --force-device-scale-factor=1")
ROOT = Path(__file__).resolve().parent.parent
from PySide6.QtCore import QRect, QTimer, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
width = int(sys.argv[2]) if len(sys.argv) > 2 else 1400
theme = sys.argv[3] if len(sys.argv) > 3 else "dark"
app = QApplication(sys.argv)
view = QWebEngineView()
view.resize(width, 900)
view.show()
FRACS = [0.0, 0.25, 0.5, 0.75]
queue = []


def js(code, cb=None):
    view.page().runJavaScript(code, 0, cb or (lambda _r: None))


def loaded(ok):
    js(f"document.documentElement.setAttribute('data-theme','{theme}'); document.documentElement.style.scrollBehavior='auto';")
    QTimer.singleShot(900, lambda: (view.grab(), QTimer.singleShot(500, lambda: (view.grab().save(str(out / "top.png")), list_demos()))))


def list_demos():
    js("JSON.stringify(Array.from(document.querySelectorAll('[data-demo]')).map(e=>e.getAttribute('data-demo')))",
       lambda r: (queue.extend((n, f) for n in json.loads(r) for f in FRACS), step()))


def step():
    if not queue:
        print("done", out)
        app.quit()
        return
    name, frac = queue.pop(0)
    code = f"""(function(){{
      var el=document.querySelector('[data-demo="{name}"]');
      el.scrollIntoView({{block:'center', behavior:'instant'}}); el.classList.remove('offscreen');
      el.getAnimations({{subtree:true}}).forEach(function(a){{a.pause(); var d=a.effect.getComputedTiming().duration; a.currentTime=d*{frac};}});
      var r=el.getBoundingClientRect(); return JSON.stringify([r.left,r.top,r.width,r.height]);
    }})()"""

    def grab(r):
        x, y, w, h = json.loads(r)
        rect = QRect(int(x), int(y), int(w), int(h))
        save = lambda: (view.grab(rect).save(str(out / f"demo-{name}-{int(frac*100):02d}.png")), step())
        QTimer.singleShot(400, lambda: (view.grab(), QTimer.singleShot(400, save)))

    js(code, grab)


view.loadFinished.connect(loaded)
view.load(QUrl.fromLocalFile(str(ROOT / "docs" / "index.html")))
app.exec()
