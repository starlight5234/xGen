"""
Global OS-Level Keyboard Hook.
Captures F3 (Inspect), F4 (Freeze Snapshot), and Esc (Cancel) globally
across Windows even when external menus or other applications have focus.
"""

from __future__ import annotations

import logging
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal
from pynput import keyboard

import time

logger = logging.getLogger("xgen.keyboard_hook")


class GlobalKeyHook(QObject):
    """
    Global low-level keyboard listener forwarding system-wide shortcuts to Qt signals.
    """
    f3_pressed = pyqtSignal()
    f4_pressed = pyqtSignal()
    esc_pressed = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._listener: Optional[keyboard.Listener] = None
        self._is_running = False
        self._last_f3_time = 0.0
        self._last_f4_time = 0.0
        self._last_esc_time = 0.0

    def start(self) -> None:
        """Start global keyboard hook in background thread."""
        if self._is_running:
            return

        try:
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                daemon=True
            )
            self._listener.start()
            self._is_running = True
            logger.info("Global keyboard hook started (F3, F4, Esc).")
        except Exception as e:
            logger.warning("Could not start global keyboard hook: %s", e)

    def stop(self) -> None:
        """Stop global keyboard hook."""
        if not self._is_running:
            return

        self._is_running = False
        if self._listener:
            try:
                self._listener.stop()
            except Exception as e:
                logger.debug("Keyboard listener stop note: %s", e)
            self._listener = None
        logger.info("Global keyboard hook stopped.")

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        """Invoked from pynput thread on any system key press with debounce protection."""
        now = time.monotonic()
        try:
            if key == keyboard.Key.f3:
                if now - self._last_f3_time >= 0.35:
                    self._last_f3_time = now
                    logger.debug("Global F3 detected.")
                    self.f3_pressed.emit()
            elif key == keyboard.Key.f4:
                if now - self._last_f4_time >= 0.35:
                    self._last_f4_time = now
                    logger.debug("Global F4 detected.")
                    self.f4_pressed.emit()
            elif key == keyboard.Key.esc:
                if now - self._last_esc_time >= 0.35:
                    self._last_esc_time = now
                    logger.debug("Global Esc detected.")
                    self.esc_pressed.emit()
        except Exception as e:
            logger.debug("Keyboard hook callback error: %s", e)
