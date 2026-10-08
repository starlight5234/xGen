"""
Scene Cache.
In-memory store of recently opened windows, popups, and menus.
Allows falling back to pre-captured hierarchies when transient UI controls
disappear before or during a click event.
Zero Qt dependencies.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from xgen.recorder.models import (
    Bounds, CapturedContext, ElementChain, ElementFacts, ProcessFacts,
    ResolutionMethod, SceneSnapshotFacts
)

logger = logging.getLogger("xgen.recorder.scene.cache")


@dataclass
class CachedSceneEntry:
    snapshot: SceneSnapshotFacts
    expires_at_mono_ms: int


class SceneCache:
    """
    Thread-safe cache holding transient window and popup snapshots.
    """
    def __init__(self, ttl_seconds: float = 4.0):
        self.ttl_seconds = ttl_seconds
        self._entries: Dict[int, CachedSceneEntry] = {}
        self._lock = threading.RLock()

    def put_snapshot(self, snapshot: SceneSnapshotFacts) -> None:
        """Stores a snapshot of an opened window or menu."""
        with self._lock:
            now_ms = int(time.monotonic() * 1000)
            expires = now_ms + int(self.ttl_seconds * 1000)
            self._entries[snapshot.window.handle] = CachedSceneEntry(
                snapshot=snapshot,
                expires_at_mono_ms=expires
            )
            self._prune_expired(now_ms)

    def remove_window(self, window_handle: int) -> None:
        """Removes a closed window from cache."""
        with self._lock:
            self._entries.pop(window_handle, None)

    def find_at_point(self, x: int, y: int) -> Optional[CapturedContext]:
        """
        Hit-tests point (x, y) against cached window snapshots.
        Returns a CapturedContext with ResolutionMethod.SCENE_CACHE if an element contains (x, y).
        """
        with self._lock:
            now_ms = int(time.monotonic() * 1000)
            self._prune_expired(now_ms)

            # Check from most recently added entry
            for handle, entry in sorted(self._entries.items(), key=lambda item: item[1].snapshot.captured_at_ms, reverse=True):
                snap = entry.snapshot
                if snap.window.bounds and not self._bounds_contain(snap.window.bounds, x, y):
                    continue

                # Find innermost element containing (x, y)
                best_elem: Optional[ElementFacts] = None
                for el in snap.elements:
                    if el.bounds and self._bounds_contain(el.bounds, x, y):
                        if best_elem is None or self._area(el.bounds) < self._area(best_elem.bounds):
                            best_elem = el

                # If no child control matched but point is within window bounds, fallback to window container
                if not best_elem and snap.window.bounds and self._bounds_contain(snap.window.bounds, x, y):
                    win_tag = "Menu" if snap.window.kind == "menu" else ("Window" if snap.window.kind == "main" else "Pane")
                    best_elem = ElementFacts(
                        control_type=win_tag,
                        name=snap.window.title,
                        class_name=snap.window.class_name,
                        bounds=snap.window.bounds,
                        native_handle=snap.window.handle
                    )

                if best_elem:
                    # Construct ancestor chain ending at window
                    chain = ElementChain(
                        target=best_elem,
                        ancestors=(),
                        window=snap.window,
                        process=ProcessFacts(pid=0),
                        complete=True
                    )
                    return CapturedContext(
                        chain=chain,
                        resolution=ResolutionMethod.SCENE_CACHE,
                        captured_at_ms=now_ms,
                        snapshot_cost_ms=0
                    )
            return None

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def count(self) -> int:
        with self._lock:
            self._prune_expired(int(time.monotonic() * 1000))
            return len(self._entries)

    def _prune_expired(self, now_ms: int) -> None:
        expired = [h for h, e in self._entries.items() if now_ms > e.expires_at_mono_ms]
        for h in expired:
            self._entries.pop(h, None)

    @staticmethod
    def _bounds_contain(b: Bounds, x: int, y: int) -> bool:
        return b.left <= x <= b.right and b.top <= y <= b.bottom

    @staticmethod
    def _area(b: Optional[Bounds]) -> int:
        if not b:
            return 999999999
        return max(0, b.right - b.left) * max(0, b.bottom - b.top)
