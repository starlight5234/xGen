"""
Passive Input Source Adapter.
Implements the InputSource port using pynput.
Hook callbacks strictly enqueue raw events in O(1) onto an internal queue;
a dedicated background dispatcher delivers events to the sink without stalling the OS hook loop.
Zero Qt dependencies.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

from pynput import keyboard, mouse
from xgen.recorder.models import RawInputEvent

logger = logging.getLogger("xgen.recorder.input")


class PassiveInputSource:
    """
    Passive OS mouse and keyboard listener.
    Captures user interactions without consuming or suppressing them.
    """
    def __init__(self, max_queue_size: int = 10000):
        self._sink: Optional[Callable[[RawInputEvent], None]] = None
        self._queue: queue.Queue[Optional[RawInputEvent]] = queue.Queue(maxsize=max_queue_size)
        self._running = False
        self._lock = threading.RLock()
        self.dropped_count: int = 0

        self._mouse_listener: Optional[mouse.Listener] = None
        self._key_listener: Optional[keyboard.Listener] = None
        self._dispatcher_thread: Optional[threading.Thread] = None

    def start(self, sink: Callable[[RawInputEvent], None]) -> None:
        """Begin listening and dispatching raw input events."""
        with self._lock:
            if self._running:
                return

            self._sink = sink
            self._running = True

            # Clear queue
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break

            # Start worker dispatcher thread
            self._dispatcher_thread = threading.Thread(
                target=self._dispatcher_loop,
                name="xgen-input-dispatcher",
                daemon=True
            )
            self._dispatcher_thread.start()

            # Start pynput listeners
            self._mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click,
                on_scroll=self._on_mouse_scroll
            )
            self._mouse_listener.daemon = True

            self._key_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self._key_listener.daemon = True

            self._mouse_listener.start()
            self._key_listener.start()
            logger.info("PassiveInputSource listeners started successfully.")

    def stop(self) -> None:
        """Stop listening and cleanly unhook from the OS."""
        with self._lock:
            if not self._running:
                return

            self._running = False

            # Stop listeners
            if self._mouse_listener:
                try:
                    self._mouse_listener.stop()
                except Exception as e:
                    logger.debug("Error stopping mouse listener: %s", e)
                self._mouse_listener = None

            if self._key_listener:
                try:
                    self._key_listener.stop()
                except Exception as e:
                    logger.debug("Error stopping key listener: %s", e)
                self._key_listener = None

            # Unblock dispatcher thread
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass

            if self._dispatcher_thread and self._dispatcher_thread.is_alive():
                self._dispatcher_thread.join(timeout=1.0)
            self._dispatcher_thread = None
            self._sink = None
            logger.info("PassiveInputSource stopped.")

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    # -------------------------------------------------------------------------
    # Hook Callbacks (Strictly O(1) Enqueue)
    # -------------------------------------------------------------------------

    def _on_mouse_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        if not self._running:
            return
        kind = "mouse_down" if pressed else "mouse_up"
        btn_name = getattr(button, "name", str(button))
        mono_ms = int(time.monotonic() * 1000)
        event = RawInputEvent(
            kind=kind,
            x=int(x),
            y=int(y),
            button=btn_name,
            monotonic_ms=mono_ms
        )
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped_count += 1
            logger.warning("Input event queue full; dropping mouse event (total dropped: %d)", self.dropped_count)

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if not self._running:
            return
        mono_ms = int(time.monotonic() * 1000)
        event = RawInputEvent(
            kind="scroll",
            x=int(x),
            y=int(y),
            dx=int(dx),
            dy=int(dy),
            monotonic_ms=mono_ms
        )
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped_count += 1
            logger.warning("Input event queue full; dropping scroll event (total dropped: %d)", self.dropped_count)

    def _on_key_press(self, key: Any) -> None:
        if not self._running:
            return
        mono_ms = int(time.monotonic() * 1000)
        k_str = self._format_key(key)
        event = RawInputEvent(
            kind="key_down",
            key_name=k_str,
            monotonic_ms=mono_ms
        )
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped_count += 1
            logger.warning("Input event queue full; dropping key_down event (total dropped: %d)", self.dropped_count)

    def _on_key_release(self, key: Any) -> None:
        if not self._running:
            return
        mono_ms = int(time.monotonic() * 1000)
        k_str = self._format_key(key)
        event = RawInputEvent(
            kind="key_up",
            key_name=k_str,
            monotonic_ms=mono_ms
        )
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped_count += 1
            logger.warning("Input event queue full; dropping key_up event (total dropped: %d)", self.dropped_count)

    @staticmethod
    def _format_key(key: Any) -> str:
        if hasattr(key, "char") and key.char is not None:
            c = key.char
            # In Windows/pynput, holding Ctrl produces ASCII control characters (< 32 or 127)
            if ord(c) < 32 or ord(c) == 127:
                if 1 <= ord(c) <= 26:
                    return chr(ord(c) + 64)  # '\x01' -> 'A', '\x1a' -> 'Z'
                if getattr(key, "vk", None) is not None:
                    vk = key.vk
                    if 65 <= vk <= 90:
                        return chr(vk)
                    if 48 <= vk <= 57:
                        return chr(vk)
                if c in ("\r", "\n"):
                    return "ENTER"
                if c == "\t":
                    return "TAB"
                if c in ("\x08", "\x7f"):
                    return "BACKSPACE"
                if c == "\x1b":
                    return "ESC"
                if c == "\x00":
                    return "SPACE"
            elif c.isprintable():
                return c

        if getattr(key, "vk", None) is not None:
            vk = key.vk
            if 65 <= vk <= 90:
                return chr(vk)
            if 48 <= vk <= 57:
                return chr(vk)
            if 96 <= vk <= 105:
                return str(vk - 96)

        if hasattr(key, "name") and key.name is not None:
            return key.name.upper()

        name = str(key)
        if name.startswith("Key."):
            name = name[4:]
        return name.upper()

    def _dispatcher_loop(self) -> None:
        """Background thread delivering events to the registered sink."""
        while self._running:
            try:
                event = self._queue.get(timeout=0.2)
                if event is None or not self._running:
                    break
                if self._sink:
                    self._sink(event)
            except queue.Empty:
                continue
            except Exception as e:
                logger.exception("Error dispatching input event: %s", e)
