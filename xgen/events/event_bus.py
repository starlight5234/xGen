"""
Central Event Bus for xGen.
Decouples UI widgets and core services using Qt Signals.
"""

from __future__ import annotations

from typing import Any, List, Optional
from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    """Singleton event bus transmitting cross-module signals across threads."""

    # Session lifecycle signals (Core -> UI)
    session_state_changed = pyqtSignal(str)          # "disconnected", "connecting", "connected", "lost"
    session_connected = pyqtSignal(object)           # SessionInfo
    session_lost = pyqtSignal()
    session_error = pyqtSignal(str)                  # Error message
    windows_updated = pyqtSignal(list)               # List[WindowInfo]

    # Tree operations (Core -> UI)
    tree_fetch_started = pyqtSignal(int)             # FetchTier enum int
    tree_fetch_progress = pyqtSignal(int, int)       # bytes_received, bytes_total
    tree_ready = pyqtSignal(str, object)             # window_handle, UINode (parsed root)
    tree_fetch_failed = pyqtSignal(str)              # error message
    large_tree_detected = pyqtSignal(int)            # node_count

    # Inspect & Selection (Capture -> UI)
    inspect_mode_toggled = pyqtSignal(bool)          # True=active, False=idle
    hover_element_changed = pyqtSignal(object)       # UIAElement
    element_selected = pyqtSignal(object, object, list)  # uia_element, uinode, list[XPathCandidate]
    transient_captured = pyqtSignal(object)          # UINode (transient subtree root)
    tree_freeze_toggled = pyqtSignal(bool)           # True=frozen

    # UI Commands -> Core Services
    request_connect = pyqtSignal(object)             # XGenConfig
    request_disconnect = pyqtSignal()
    request_switch_window = pyqtSignal(str)          # window_handle
    request_refresh_tree = pyqtSignal(str)           # window_handle
    request_scoped_fetch = pyqtSignal(str, str)      # window_handle, element_id
    request_activate_inspect = pyqtSignal()
    request_deactivate_inspect = pyqtSignal()
    request_freeze_snapshot = pyqtSignal(int, int)   # cursor x, y
    request_start_timed_capture = pyqtSignal(int)    # delay_seconds
    request_set_tree_frozen = pyqtSignal(bool)       # frozen

    _instance: Optional[EventBus] = None

    @classmethod
    def instance(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = EventBus()
        return cls._instance
