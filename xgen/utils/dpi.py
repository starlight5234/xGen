"""
Windows DPI Awareness and scaling helpers.
"""

from __future__ import annotations

import ctypes
import logging
import platform

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication

from xgen.utils.rect import Rect

logger = logging.getLogger("xgen.dpi")


def init_dpi_awareness() -> None:
    """
    Initialize Windows per-monitor DPI awareness before any UI or window creation.
    Sets PROCESS_PER_MONITOR_DPI_AWARE_V2 (-4).
    """
    if platform.system() != "Windows":
        return

    try:
        user32 = ctypes.windll.user32
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 is -4
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
            res = user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
            if res:
                logger.debug("SetProcessDpiAwarenessContext(PER_MONITOR_V2) succeeded.")
                return

        # Fallback to SetProcessDpiAwareness(2) from shcore.dll
        shcore = ctypes.windll.shcore
        if hasattr(shcore, "SetProcessDpiAwareness"):
            shcore.SetProcessDpiAwareness(2)
            logger.debug("SetProcessDpiAwareness(2) succeeded.")
            return

        # Fallback to legacy SetProcessDPIAware from user32
        user32.SetProcessDPIAware()
        logger.debug("SetProcessDPIAware() legacy succeeded.")
    except Exception as e:
        logger.warning("Failed to set DPI awareness: %s", e)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_physical_cursor_pos() -> tuple[int, int]:
    """
    Return the current mouse cursor position in physical screen coordinates.
    Works universally across all Windows versions (7, 8, 10, 11) via native Win32 GetCursorPos.
    """
    if platform.system() == "Windows":
        try:
            pt = POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return int(pt.x), int(pt.y)
        except Exception:
            pass

    # Fallback using Qt logical position converted to physical
    pos = QCursor.pos()
    dpr = get_screen_dpr_at(pos.x(), pos.y())
    return int(pos.x() * dpr), int(pos.y() * dpr)


def get_screen_dpr_at(x: int, y: int) -> float:
    """Return the device pixel ratio (scaling factor e.g. 1.0, 1.25, 1.5, 2.0) for the screen at (x, y)."""
    app = QApplication.instance()
    if not app:
        return 1.0

    # 1. Match physical screen bounds across all active displays
    screens = app.screens()
    for s in screens:
        dpr = float(s.devicePixelRatio()) or 1.0
        geom = s.geometry()  # logical geometry
        phys_left = int(geom.x() * dpr)
        phys_top = int(geom.y() * dpr)
        phys_right = phys_left + int(geom.width() * dpr)
        phys_bottom = phys_top + int(geom.height() * dpr)
        if phys_left <= x < phys_right and phys_top <= y < phys_bottom:
            return dpr
        if geom.left() <= x < geom.right() and geom.top() <= y < geom.bottom():
            return dpr

    screen = app.screenAt(QPoint(x, y))
    if screen is not None:
        return float(screen.devicePixelRatio())

    primary = app.primaryScreen()
    return float(primary.devicePixelRatio()) if primary else 1.0


def physical_to_logical_rect(rect: Rect) -> Rect:
    """Convert physical screen pixels (from UIA) to Qt logical coordinates accounting for per-monitor DPI."""
    dpr = get_screen_dpr_at(rect.left, rect.top)
    if dpr == 1.0 or dpr <= 0.0:
        return rect

    lx = int(rect.left / dpr)
    ly = int(rect.top / dpr)
    lw = int(rect.width / dpr)
    lh = int(rect.height / dpr)
    return Rect(lx, ly, lx + lw, ly + lh)


def get_dpi_for_window(hwnd: int) -> int:
    """Return the DPI for the specified window handle (HWND). Defaults to 96."""
    if platform.system() != "Windows" or not hwnd:
        return 96
    try:
        user32 = ctypes.windll.user32
        if hasattr(user32, "GetDpiForWindow"):
            dpi = user32.GetDpiForWindow(hwnd)
            if dpi > 0:
                return int(dpi)
    except Exception:
        pass
    return 96


def get_scale_factor_for_window(hwnd: int) -> float:
    """Return the DPI scale factor (e.g. 1.0, 1.25, 1.5, 2.0) for the window."""
    return get_dpi_for_window(hwnd) / 96.0
