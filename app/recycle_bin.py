"""Windows Recycle Bin: query its contents and empty it (Shell API via ctypes).

Emptying the bin deletes files permanently, so callers must get the user's confirmation first;
the app does that with its own dialog and then calls :func:`empty` without the shell prompt.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

SHERB_NOCONFIRMATION = 0x1
SHERB_NOPROGRESSUI = 0x2
SHERB_NOSOUND = 0x4


class RecycleBinError(RuntimeError):
    pass


class _SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_int64), ("i64NumItems", ctypes.c_int64)]


def _shell32():
    if sys.platform != "win32":
        raise RecycleBinError("The Recycle Bin is only supported on Windows")
    return ctypes.windll.shell32


def query() -> tuple[int, int]:
    """Return (number of items, total bytes) in the Recycle Bin of all drives."""
    info = _SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(_SHQUERYRBINFO)
    hr = _shell32().SHQueryRecycleBinW(None, ctypes.byref(info))
    if hr != 0:
        raise RecycleBinError(f"Could not read the Recycle Bin (error 0x{hr & 0xFFFFFFFF:08X})")
    return int(info.i64NumItems), int(info.i64Size)


def empty() -> int:
    """Permanently delete everything in the Recycle Bin. Returns the number of items deleted.

    No shell confirmation is shown - confirm with the user before calling this.
    """
    items, _size = query()
    if items == 0:
        return 0
    flags = SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
    hr = _shell32().SHEmptyRecycleBinW(None, None, flags)
    if hr != 0:
        raise RecycleBinError(f"Could not empty the Recycle Bin (error 0x{hr & 0xFFFFFFFF:08X})")
    return items


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"  # pragma: no cover
