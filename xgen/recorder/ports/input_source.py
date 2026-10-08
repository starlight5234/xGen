from __future__ import annotations

from typing import Callable, Protocol
from xgen.recorder.models import RawInputEvent


class InputSource(Protocol):
    """
    Passive OS input event listener.
    Must enqueue raw mouse/keyboard events in O(1) without blocking.
    """
    def start(self, sink: Callable[[RawInputEvent], None]) -> None:
        """Begin listening and dispatching raw input events to the sink callback."""
        ...

    def stop(self) -> None:
        """Stop listening and cleanly unhook from the OS."""
        ...

    def is_running(self) -> bool:
        """Returns True if the hook listener thread is active."""
        ...
