"""
System Clock Adapter.
Implements the Clock port using standard library time and datetime.
Zero Qt dependencies.
"""
from __future__ import annotations

import datetime
import time


class SystemClock:
    """Provides high-resolution monotonic and UTC wall-clock time."""

    def monotonic_ms(self) -> int:
        """Returns monotonic timestamp in integer milliseconds."""
        return int(time.monotonic() * 1000)

    def wall_time_iso(self) -> str:
        """Returns current UTC timestamp in ISO 8601 format."""
        return datetime.datetime.now(datetime.timezone.utc).isoformat()
