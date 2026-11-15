# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for HandGestureMouse.exe.

Build with build.bat (or: pyinstaller build/pyinstaller.spec --distpath dist --workpath build/work).
Produces a self-contained folder dist/HandGestureMouse/ containing HandGestureMouse.exe; Python does
not need to be installed on the target machine.
"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 - provided by PyInstaller


def p(*parts):
    return os.path.join(ROOT, *parts)


# MediaPipe Tasks loads its native library with ctypes from the mediapipe.tasks.c package
# (importlib.resources), so the DLL must sit at mediapipe/tasks/c/ inside the bundle.
import mediapipe  # noqa: E402

MP_DIR = os.path.dirname(mediapipe.__file__)
mp_binaries = [(os.path.join(MP_DIR, "tasks", "c", "libmediapipe.dll"), os.path.join("mediapipe", "tasks", "c"))]

datas = [
    (p("models", "hand_landmarker.task"), "models"),
    (p("ui", "assets"), os.path.join("ui", "assets")),
    (p("config", "settings.json"), "config"),
    (p("config", "gestures.json"), "config"),
    (p("docs"), "docs"),
]
datas += collect_data_files("mediapipe", excludes=["**/*.pyc", "**/testdata/**"])

hiddenimports = [
    "mediapipe.tasks.c",
    "mediapipe.tasks.python.vision.hand_landmarker",
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
]
hiddenimports += collect_submodules("mediapipe.tasks.python", filter=lambda name: ".genai" not in name)

excludes = [
    "PIL", "pyscreeze", "pymsgbox", "tkinter", "matplotlib", "pandas", "scipy", "IPython", "jupyter", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
    "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtPdf", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSensors",
]

a = Analysis(  # noqa: F821
    [p("main.py")],
    pathex=[ROOT],
    binaries=mp_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
# Drop Qt pieces this widgets-only app never loads (saves ~45 MB).
_UNUSED = ("opengl32sw.dll", "Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6VirtualKeyboard", "qpdf.dll", "Qt6OpenGL.dll")
a.binaries = [b for b in a.binaries if not any(u.lower() in os.path.basename(b[0]).lower() for u in _UNUSED)]
a.datas = [d for d in a.datas if "PySide6" + os.sep + "translations" not in d[0] and "PySide6/translations" not in d[0]]

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HandGestureMouse",
    icon=p("ui", "assets", "icon.ico"),
    console=False,
    disable_windowed_traceback=False,
    upx=False,
    version=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="HandGestureMouse",
)
