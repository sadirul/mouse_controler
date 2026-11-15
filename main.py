"""Hand Gesture Mouse - entry point.

    python main.py                 # open the dashboard
    python main.py --minimized     # start in the system tray
    python main.py --start-tracking
"""
import sys

from app.application import run

if __name__ == "__main__":
    sys.exit(run())
