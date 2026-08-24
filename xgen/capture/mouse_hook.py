"""
Global Mouse Hook using pynput.
Intercepts left-click coordinates during Inspect Mode and suppresses clicks on target applications
so inspected controls are selected in xGen without triggering their native action in the target app.
"""

from __future__ import annotations

import logging
import platform
from typing import Callable, Optional
from PyQt6.QtCore import QObject, pyqtSignal
from pynput import mouse

logger = logging.getLogger("xgen.mouse_hook")

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2


class MouseHook(QObject):
    """
    Global low-level mouse hook emitting signals on left-click and intercepting clicks on target apps.
    """
    left_clicked = pyqtSignal(int, int)   # screen_x, screen_y

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._listener: Optional[mouse.Listener] = None
        self._filter: Optional[Callable[[int, int], bool]] = None
        self._is_active = False

    def start(self, callback_filter: Optional[Callable[[int, int], bool]] = None) -> None:
        """
        Start the background mouse listener thread with event suppression on target apps.
        callback_filter: Return True if outside xGen (intercept click), False if inside xGen (allow click).
        """
        self.stop()
        self._filter = callback_filter
        self._is_active = True

        if platform.system() == "Windows":
            self._listener = mouse.Listener(
                on_click=self._on_click,
                win32_event_filter=self._win32_event_filter
            )
        else:
            self._listener = mouse.Listener(on_click=self._on_click)

        self._listener.daemon = True
        self._listener.start()
        logger.debug("Global mouse hook started with click interception.")

    def stop(self) -> None:
        """Stop and terminate background mouse listener."""
        self._is_active = False
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception as e:
                logger.debug("Mouse listener stop note: %s", e)
            self._listener = None
            logger.debug("Global mouse hook stopped.")

    def _win32_event_filter(self, msg: int, data: object) -> bool:
        """
        Windows low-level hook filter.
        Calls suppress_event() to completely block clicks from reaching the target application.
        """
        if not self._is_active:
            return True

        if msg in (WM_LBUTTONDOWN, WM_LBUTTONUP, WM_NCLBUTTONDOWN, WM_NCLBUTTONUP):
            px = int(data.pt.x)
            py = int(data.pt.y)

            # If filter returns False (click is inside xGen window), allow click through!
            if self._filter is not None and not self._filter(px, py):
                return True

            # Click is on target app: emit selection on button down
            if msg in (WM_LBUTTONDOWN, WM_NCLBUTTONDOWN):
                self.left_clicked.emit(px, py)

            # Suppress click event from reaching target application in Windows
            if self._listener is not None:
                self._listener.suppress_event()

            return False

        return True

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        """Fallback callback for non-Windows platforms."""
        if platform.system() == "Windows":
            return None

        if not self._is_active or not pressed or button != mouse.Button.left:
            return None

        if self._filter is not None and not self._filter(x, y):
            return None

        self.left_clicked.emit(int(x), int(y))
        return None
