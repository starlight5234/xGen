"""
Windows Scene Event Source Adapter.
Implements the SceneEventSource port using SetWinEventHook to monitor popup and menu displays.
Zero Qt dependencies.
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes
from typing import Callable, List, Optional

try:
    import uiautomation as auto
    user32 = ctypes.windll.user32
    HAS_WINDOWS_DEPS = True
except (ImportError, AttributeError):
    auto = None
    user32 = None
    HAS_WINDOWS_DEPS = False

from xgen.recorder.models import (
    Bounds, ElementFacts, SceneEvent, SceneSnapshotFacts, WindowFacts
)

logger = logging.getLogger("xgen.recorder.scene.windows")

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_SYSTEM_MENUPOPUPSTART = 0x0006
EVENT_SYSTEM_MENUPOPUPEND = 0x0007
EVENT_OBJECT_SHOW = 0x8002

WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002

if hasattr(ctypes, "WINFUNCTYPE"):
    WINEVENTPROC = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        wintypes.LONG,
        wintypes.LONG,
        wintypes.DWORD,
        wintypes.DWORD
    )
else:
    WINEVENTPROC = ctypes.CFUNCTYPE(None)


class WindowsSceneEventSource:
    """
    Monitors OS-level window and popup show events via SetWinEventHook.
    """
    def __init__(self):
        self._sink: Optional[Callable[[SceneEvent], None]] = None
        self._running = False
        self._hook_thread: Optional[threading.Thread] = None
        self._thread_id: int = 0
        self._lock = threading.RLock()
        self._hook_fn = None  # Retain ctypes reference

    def start(self, sink: Callable[[SceneEvent], None]) -> None:
        with self._lock:
            if self._running:
                return
            self._sink = sink
            self._running = True

            ready_event = threading.Event()
            self._hook_thread = threading.Thread(
                target=self._hook_loop,
                args=(ready_event,),
                name="xgen-scene-hook",
                daemon=True
            )
            self._hook_thread.start()
            ready_event.wait(timeout=2.0)

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            if self._thread_id:
                WM_QUIT = 0x0012
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            if self._hook_thread and self._hook_thread.is_alive():
                self._hook_thread.join(timeout=1.0)
            self._hook_thread = None
            self._sink = None

    def snapshot(self, window_handle: int, *, deadline_ms: int = 200) -> Optional[SceneSnapshotFacts]:
        """Captures a snapshot of the controls in the window."""
        t0 = time.monotonic()
        try:
            win_ctrl = auto.ControlFromHandle(window_handle)
            if not win_ctrl or not win_ctrl.Exists(0):
                return None

            title = str(getattr(win_ctrl, "Name", "") or "")
            cls_name = str(getattr(win_ctrl, "ClassName", "") or "")
            rect = getattr(win_ctrl, "BoundingRectangle", None)
            w_bounds = Bounds(rect.left, rect.top, rect.right, rect.bottom) if rect else None
            win_facts = WindowFacts(handle=window_handle, title=title, class_name=cls_name, bounds=w_bounds)

            elements: List[ElementFacts] = []
            deadline = t0 + (deadline_ms / 1000.0)

            def walk(c: auto.Control, depth: int = 0):
                if time.monotonic() > deadline or depth > 4:
                    return
                for child in c.GetChildren():
                    c_type = child.ControlTypeName.replace("Control", "")
                    c_rect = getattr(child, "BoundingRectangle", None)
                    b = Bounds(c_rect.left, c_rect.top, c_rect.right, c_rect.bottom) if c_rect else None
                    el = ElementFacts(
                        control_type=c_type,
                        name=str(child.Name or ""),
                        automation_id=str(child.AutomationId or ""),
                        class_name=str(child.ClassName or ""),
                        bounds=b,
                        is_password=bool(getattr(child, "IsPassword", False)),
                        native_handle=int(child.NativeWindowHandle or 0)
                    )
                    elements.append(el)
                    walk(child, depth + 1)

            # Add root window container itself so hit-testing succeeds even on single-container popups
            root_el = ElementFacts(
                control_type="Window",
                name=title,
                automation_id=str(getattr(win_ctrl, "AutomationId", "") or ""),
                class_name=cls_name,
                bounds=w_bounds,
                native_handle=window_handle
            )
            elements.append(root_el)

            walk(win_ctrl)
            now_ms = int(time.monotonic() * 1000)
            return SceneSnapshotFacts(
                window=win_facts,
                elements=tuple(elements),
                captured_at_ms=now_ms
            )
        except Exception as e:
            logger.debug("Failed to snapshot window 0x%X: %s", window_handle, e)
            return None

    def _hook_loop(self, ready_event: threading.Event) -> None:
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        def win_event_callback(hWinEventHook, event, hwnd, idObject, idChild, idEventThread, dwmsEventTime):
            if not self._running or not hwnd or not self._sink:
                return
            # idObject == 0 (OBJID_WINDOW) or OBJID_CLIENT
            if idObject != 0:
                return

            if event == EVENT_SYSTEM_MENUPOPUPSTART:
                kind = "menu_open"
            elif event == EVENT_OBJECT_SHOW:
                # Only capture top-level and popup windows; ignore child controls with WS_CHILD
                GWL_STYLE = -16
                WS_CHILD = 0x40000000
                try:
                    style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_STYLE)
                    if isinstance(style, int):
                        if style & WS_CHILD:
                            return
                    else:
                        parent = user32.GetParent(hwnd)
                        if parent:
                            return
                except Exception:
                    pass
                kind = "popup_open"
            else:
                kind = "window_open"
            now_ms = int(time.monotonic() * 1000)
            
            # Read title
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)

            scene_ev = SceneEvent(
                kind=kind,
                window_handle=int(hwnd),
                title=buf.value,
                monotonic_ms=now_ms
            )
            try:
                self._sink(scene_ev)
            except Exception as e:
                logger.debug("Error in scene event sink: %s", e)

        self._hook_fn = WINEVENTPROC(win_event_callback)
        flags = WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS

        # Hook menu popup events
        h_hook1 = user32.SetWinEventHook(
            EVENT_SYSTEM_MENUPOPUPSTART,
            EVENT_SYSTEM_MENUPOPUPEND,
            0,
            self._hook_fn,
            0,
            0,
            flags
        )

        # Hook transient popup / tooltip / combobox dropdown show events
        h_hook2 = user32.SetWinEventHook(
            EVENT_OBJECT_SHOW,
            EVENT_OBJECT_SHOW,
            0,
            self._hook_fn,
            0,
            0,
            flags
        )

        ready_event.set()

        # Windows message loop
        msg = wintypes.MSG()
        while self._running:
            b_ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if b_ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if h_hook1:
            user32.UnhookWinEvent(h_hook1)
        if h_hook2:
            user32.UnhookWinEvent(h_hook2)
