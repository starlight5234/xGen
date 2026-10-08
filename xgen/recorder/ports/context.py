from __future__ import annotations

from typing import Optional, Protocol, Sequence, Tuple
from xgen.recorder.models import CapturedContext, ContextCapabilities, SimilarFacts, WindowFacts


class NativeContextProvider(Protocol):
    """
    Retrieves native UI hierarchy, element properties, and window context.
    Encapsulates OS-specific accessibility queries (UIA / AX).
    """
    def capabilities(self) -> ContextCapabilities:
        """Returns capabilities of the native provider."""
        ...

    def cursor_position(self) -> Tuple[int, int]:
        """Returns current screen coordinates (x, y) of the mouse pointer."""
        ...

    def capture_at(self, x: int, y: int, *, deadline_ms: int) -> Optional[CapturedContext]:
        """
        Hit-tests element at (x, y) and resolves its ancestor chain.
        Returns None if query times out or element is unreachable.
        """
        ...

    def capture_focused(self, *, deadline_ms: int) -> Optional[CapturedContext]:
        """
        Resolves the currently focused keyboard element and its ancestor chain.
        """
        ...

    def find_similar(self, ctx: CapturedContext, *, limit: int, deadline_ms: int) -> SimilarFacts:
        """
        Queries sibling or duplicate elements sharing similar tags/names in the window.
        """
        ...

    def window_still_exists(self, window_handle: int) -> bool:
        """Returns True if the window handle is still active on the desktop."""
        ...

    def same_title_windows(self, window: WindowFacts) -> int:
        """Returns count of open desktop windows with identical titles."""
        ...

    def process_of_point(self, x: int, y: int) -> Optional[int]:
        """Returns the PID owning the window under point (x, y)."""
        ...
