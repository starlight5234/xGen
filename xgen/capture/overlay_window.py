"""
Highlight Overlay Window.
Transparent, click-through, always-on-top frameless window drawing a bounding rectangle.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import platform
from typing import Optional
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QPaintEvent, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from xgen.utils.dpi import physical_to_logical_rect
from xgen.utils.rect import Rect

logger = logging.getLogger("xgen.overlay")

# Win32 Constants
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040


class OverlayWindow(QWidget):
    """
    Click-through highlight overlay window tracking hovered and selected element bounds.
    """
    HOVER_FILL = QColor(255, 68, 68, 50)        # semi-transparent coral
    HOVER_BORDER = QColor(255, 40, 40, 255)    # solid coral border

    SELECTED_FILL = QColor(0, 150, 255, 50)     # semi-transparent electric blue
    SELECTED_BORDER = QColor(0, 150, 255, 255)  # solid electric blue

    TESTED_FILL = QColor(16, 185, 129, 70)      # semi-transparent neon emerald
    TESTED_BORDER = QColor(16, 185, 129, 255)   # solid neon emerald border
    BORDER_WIDTH = 3

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._style_mode = "hover"  # "hover" | "selected" | "tested"
        self._current_rect: Optional[Rect] = None

    @property
    def style_mode(self) -> str:
        return self._style_mode

    def highlight_hover(self, rect: Optional[Rect]) -> None:
        """Display hover bounding box in coral highlight."""
        self._style_mode = "hover"
        self.move_to(rect)

    def highlight_selected(self, rect: Optional[Rect]) -> None:
        """Display selected bounding box in electric blue highlight."""
        self._style_mode = "selected"
        self.move_to(rect)

    def highlight_tested(self, rect: Optional[Rect]) -> None:
        """Display test-verified bounding box in vibrant emerald green highlight."""
        self._style_mode = "tested"
        self.move_to(rect)

    def move_to(self, rect: Optional[Rect]) -> None:
        """Move and resize the overlay widget to match target element bounding box, accounting for DPI zoom."""
        if rect is None or rect.width <= 0 or rect.height <= 0:
            self.hide_overlay()
            return

        # Do not overlay full-screen desktop background to avoid flooding display with blue
        if self._is_fullscreen_rect(rect):
            self.hide_overlay()
            return

        self._current_rect = rect

        # Convert physical monitor pixels to Qt logical DPI coordinates
        log_rect = physical_to_logical_rect(rect)

        # Inset / expand slightly so border encloses element (allow negative coords on secondary monitors)
        gx = log_rect.left - 2
        gy = log_rect.top - 2
        gw = max(4, log_rect.width + 4)
        gh = max(4, log_rect.height + 4)

        self.setGeometry(gx, gy, gw, gh)

        if not self.isVisible():
            self.show()
            self._apply_native_styles()

        self._enforce_topmost()
        self.raise_()
        self.update()

    def _is_fullscreen_rect(self, rect: Rect) -> bool:
        """Check if bounding rect covers the entire monitor screen."""
        app = QApplication.instance()
        if not app:
            return False
        cx = rect.left + rect.width // 2
        cy = rect.top + rect.height // 2
        screen = app.screenAt(QPoint(cx, cy)) or app.primaryScreen()
        if screen:
            geom = screen.geometry()
            dpr = screen.devicePixelRatio() or 1.0
            phys_w = int(geom.width() * dpr)
            phys_h = int(geom.height() * dpr)
            # If rect spans the whole monitor from corner to corner
            if abs(rect.left - int(geom.left() * dpr)) <= 10 and abs(rect.top - int(geom.top() * dpr)) <= 10:
                if rect.width >= (phys_w - 40) and rect.height >= (phys_h - 40):
                    return True
        return False

    def hide_overlay(self) -> None:
        """Hide overlay without destroying."""
        self._current_rect = None
        self.hide()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw filled highlight rectangle and crisp border based on active mode."""
        if not self._current_rect:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        if self._style_mode == "tested":
            fill_color = self.TESTED_FILL
            border_color = self.TESTED_BORDER
        elif self._style_mode == "hover":
            fill_color = self.HOVER_FILL
            border_color = self.HOVER_BORDER
        else:
            fill_color = self.SELECTED_FILL
            border_color = self.SELECTED_BORDER

        # Draw semi-transparent background fill
        painter.fillRect(self.rect(), fill_color)

        # Draw crisp solid outer border
        pen = QPen(border_color, self.BORDER_WIDTH)
        painter.setPen(pen)
        draw_rect = self.rect().adjusted(1, 1, -2, -2)
        painter.drawRect(draw_rect)

    def _apply_native_styles(self) -> None:
        """Apply Win32 WS_EX_TRANSPARENT safely without disrupting Qt alpha compositing."""
        if platform.system() != "Windows":
            return

        try:
            hwnd = wintypes.HWND(int(self.winId()))
            user32 = ctypes.windll.user32
            get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            get_long.restype = ctypes.c_long
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
            set_long.restype = ctypes.c_long

            cur_style = get_long(hwnd, GWL_EXSTYLE)
            new_style = cur_style | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
            set_long(hwnd, GWL_EXSTYLE, new_style)
        except Exception as e:
            logger.debug("Could not apply native styles: %s", e)

    def _enforce_topmost(self) -> None:
        """Raise window to the top of the Z-band above context menus without overriding Qt DPI geometry."""
        if platform.system() != "Windows":
            return

        try:
            hwnd = wintypes.HWND(int(self.winId()))
            user32 = ctypes.windll.user32
            user32.SetWindowPos.argtypes = [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            user32.SetWindowPos.restype = wintypes.BOOL
            _HWND_TOPMOST = wintypes.HWND(ctypes.c_void_p(-1).value)
            user32.SetWindowPos(
                hwnd,
                _HWND_TOPMOST,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
            )
        except Exception as e:
            logger.debug("SetWindowPos topmost note: %s", e)

