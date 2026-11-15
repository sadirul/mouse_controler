@echo off
REM ---------------------------------------------------------------------------
REM  Build HandGestureMouse.exe (standalone - no Python needed on the target PC)
REM
REM    build.bat            build into dist\HandGestureMouse\
REM    build.bat clean      remove previous build output first
REM
REM  Requires Python 3.10+ on the BUILD machine only.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if /i "%1"=="clean" (
    echo Removing previous build output...
    rmdir /s /q dist 2>nul
    rmdir /s /q build\work 2>nul
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH. Install Python 3.10+ from python.org.
    exit /b 1
)

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error

echo Installing dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt -r requirements-dev.txt || goto :error

if not exist models\hand_landmarker.task (
    echo Downloading MediaPipe hand landmarker model...
    curl -L -o models\hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task || goto :error
)

echo Running unit tests...
python -m pytest -q || goto :error

echo Building executable...
python -m PyInstaller build\pyinstaller.spec --noconfirm --distpath dist --workpath build\work || goto :error

echo.
echo ===========================================================================
echo  Build complete:  dist\HandGestureMouse\HandGestureMouse.exe
echo  Distribute the whole dist\HandGestureMouse folder (zip it).
echo ===========================================================================
exit /b 0

:error
echo.
echo [ERROR] Build failed - see the messages above.
exit /b 1
