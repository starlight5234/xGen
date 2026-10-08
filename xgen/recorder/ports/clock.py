from __future__ import annotations

from typing import Protocol


class Clock(Protocol):
    """Provides time measurements for timestamps and debounce logic."""
    def monotonic_ms(self) -> int:
        """Returns monotonic timestamp in milliseconds."""
        ...

    def wall_time_iso(self) -> str:
        """Returns wall-clock ISO 8601 formatted timestamp string."""
        ...
