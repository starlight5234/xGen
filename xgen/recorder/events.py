"""
Recorder Event System.
Thread-safe in-process event bus for streaming notifications to clients (GUI, CLI, MCP).
Zero Qt dependencies.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Type, TypeVar

from xgen.recorder.models import RecorderState, Step

logger = logging.getLogger("xgen.recorder.events")


@dataclass(frozen=True)
class RecorderEvent:
    """Base class for all recorder domain events."""
    pass


@dataclass(frozen=True)
class StateChangedEvent(RecorderEvent):
    old_state: RecorderState
    new_state: RecorderState
    recording_id: str = ""


@dataclass(frozen=True)
class StepRecordedEvent(RecorderEvent):
    recording_id: str
    step: Step


@dataclass(frozen=True)
class StepUpdatedEvent(RecorderEvent):
    recording_id: str
    step: Step


@dataclass(frozen=True)
class StepDeletedEvent(RecorderEvent):
    recording_id: str
    step_id: str


@dataclass(frozen=True)
class WarningEvent(RecorderEvent):
    code: str
    message: str
    recording_id: str = ""


@dataclass(frozen=True)
class ErrorEvent(RecorderEvent):
    code: str
    message: str
    recording_id: str = ""


@dataclass(frozen=True)
class VerificationProgressEvent(RecorderEvent):
    job_id: str
    recording_id: str
    completed_steps: int
    total_steps: int


@dataclass(frozen=True)
class VerificationCompletedEvent(RecorderEvent):
    job_id: str
    recording_id: str
    passed_count: int
    failed_count: int
    unverifiable_count: int


TEvent = TypeVar("TEvent", bound=RecorderEvent)


class EventBus:
    """
    Thread-safe synchronous event bus.
    Subscribers receive typed domain events when published.
    """
    def __init__(self):
        self._subscribers: Dict[Type[RecorderEvent], List[Callable[[Any], None]]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: Type[TEvent], handler: Callable[[TEvent], None]) -> Callable[[], None]:
        """
        Register an event handler. Returns an unsubscribe callable.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)

        def unsubscribe():
            with self._lock:
                if event_type in self._subscribers:
                    try:
                        self._subscribers[event_type].remove(handler)
                    except ValueError:
                        pass
        return unsubscribe

    def publish(self, event: RecorderEvent) -> None:
        """
        Publish an event to all subscribers registered for its type or base class.
        Handlers are executed safely; exceptions in handlers are logged and suppressed.
        """
        handlers_to_call: List[Callable[[Any], None]] = []
        with self._lock:
            for registered_type, handlers in self._subscribers.items():
                if isinstance(event, registered_type):
                    handlers_to_call.extend(handlers)

        for handler in handlers_to_call:
            try:
                handler(event)
            except Exception as e:
                logger.exception("Error executing event handler for %s: %s", type(event).__name__, e)
