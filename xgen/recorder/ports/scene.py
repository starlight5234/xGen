from __future__ import annotations

from typing import Callable, Optional, Protocol
from xgen.recorder.models import SceneEvent, SceneSnapshotFacts


class SceneEventSource(Protocol):
    """
    Watches OS window creation and popup/menu show events (e.g. SetWinEventHook).
    Used to pre-cache transient UI hierarchies before click events dismiss them.
    """
    def start(self, sink: Callable[[SceneEvent], None]) -> None:
        """Starts watching OS window/menu lifecycle events."""
        ...

    def stop(self) -> None:
        """Stops watching events."""
        ...

    def snapshot(self, window_handle: int, *, deadline_ms: int) -> Optional[SceneSnapshotFacts]:
        """Captures a lightweight snapshot of the window's top-level controls."""
        ...
