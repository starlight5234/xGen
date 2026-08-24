"""
Bounding Rectangle utilities and hit-testing helpers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Rect:
    """Represents a 2D bounding rectangle in screen coordinates."""
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height

    def contains_point(self, x: int, y: int) -> bool:
        """Return True if point (x, y) is inside the rectangle bounds."""
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    def intersects(self, other: Rect) -> bool:
        """Return True if this rectangle overlaps with another rectangle."""
        return not (
            self.right < other.left
            or self.left > other.right
            or self.bottom < other.top
            or self.top > other.bottom
        )

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    @classmethod
    def from_appium_string(cls, s: str) -> Optional[Rect]:
        """
        Parse Appium / WinAppDriver BoundingRectangle attribute format:
        e.g. "[100,200][250,230]" or "{l:100, t:200, r:250, b:230}"
        Returns Rect instance or None if invalid.
        """
        if not s or not isinstance(s, str):
            return None

        # Pattern 1: [left,top][right,bottom] or [left, top][right, bottom]
        match = re.match(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]", s.strip())
        if match:
            left, top, right, bottom = map(int, match.groups())
            return cls(left=left, top=top, right=right, bottom=bottom)

        # Pattern 2: comma-separated "left,top,width,height" or "left,top,right,bottom"
        parts = re.findall(r"-?\d+", s)
        if len(parts) == 4:
            nums = list(map(int, parts))
            # If 3rd/4th numbers look like width/height (positive and small) vs coordinates
            return cls(left=nums[0], top=nums[1], right=nums[2], bottom=nums[3])

        return None
