"""
Qt Event Bridge for xGen Recorder.
Subscribes to headless RecorderApi / EventBus and re-emits events as native PyQt6 signals
on the GUI thread for responsive UI updates.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from PyQt6.QtCore import QObject, pyqtSignal

from xgen.recorder.api import RecorderApi
from xgen.recorder.events import (
    ErrorEvent, RecorderEvent, StateChangedEvent, StepDeletedEvent,
    StepRecordedEvent, StepUpdatedEvent, WarningEvent
)

logger = logging.getLogger("xgen.ui.recorder.bridge")


class RecorderQtBridge(QObject):
    """
    Bridges backend recorder events from worker/bus threads to Qt signals.
    """
    state_changed = pyqtSignal(str)        # new_state value (e.g. "recording", "idle")
    step_added = pyqtSignal(object)        # Step dataclass
    step_updated = pyqtSignal(object)      # Step dataclass
    step_removed = pyqtSignal(str)         # step_id
    warning = pyqtSignal(str, str)         # code, message
    error = pyqtSignal(str, str)           # code, message

    def __init__(self, api: RecorderApi, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.api = api
        self._unsub: Optional[Callable[[], None]] = None
        self._subscribe()

    def _subscribe(self) -> None:
        try:
            self._unsub = self.api.subscribe(self._on_bus_event)
        except Exception as e:
            logger.warning("Failed to subscribe RecorderQtBridge to RecorderApi: %s", e)

    def _on_bus_event(self, event: RecorderEvent) -> None:
        """Dispatches bus event to appropriate Qt signal."""
        try:
            if isinstance(event, StateChangedEvent):
                self.state_changed.emit(event.new_state.value)
            elif isinstance(event, StepRecordedEvent):
                self.step_added.emit(event.step)
            elif isinstance(event, StepUpdatedEvent):
                self.step_updated.emit(event.step)
            elif isinstance(event, StepDeletedEvent):
                self.step_removed.emit(event.step_id)
            elif isinstance(event, WarningEvent):
                self.warning.emit(event.code, event.message)
            elif isinstance(event, ErrorEvent):
                self.error.emit(event.code, event.message)
        except Exception as e:
            logger.debug("Error in RecorderQtBridge event dispatch: %s", e)

    def dispose(self) -> None:
        """Unsubscribes from backend bus."""
        if self._unsub:
            try:
                self._unsub()
            except Exception:
                pass
            self._unsub = None
