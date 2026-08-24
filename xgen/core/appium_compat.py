"""
Appium Windows Driver XPath Compatibility & Readability Normalization Layer.
Ensures every candidate conforms strictly to the supported XPath 1.0 subset in Appium Windows Driver / WinAppDriver.
"""

from __future__ import annotations

import re
from typing import List


class AppiumXPathCompatLayer:
    """Validates syntax compatibility and normalizes formatting of XPath selectors."""

    # Disallowed unbounded or unsupported axes/functions in Appium Windows Driver XPath 1.0 engine
    DISALLOWED_PATTERNS: List[re.Pattern] = [
        re.compile(r"(?<!-)following::", re.IGNORECASE),
        re.compile(r"(?<!-)preceding::", re.IGNORECASE),
        re.compile(r"\bancestor::", re.IGNORECASE),
        re.compile(r"\bmatches\(", re.IGNORECASE),
        re.compile(r"\blower-case\(", re.IGNORECASE),
        re.compile(r"\bupper-case\(", re.IGNORECASE),
        re.compile(r"\bends-with\(", re.IGNORECASE),
        re.compile(r"\breplace\(", re.IGNORECASE),
    ]

    @classmethod
    def is_appium_compatible(cls, xpath: str) -> bool:
        """
        Check if the given XPath selector is supported by Appium Windows Driver (WinAppDriver).
        """
        if not xpath or not xpath.strip():
            return False

        # Reject unsupported functions or unbounded axes
        for pattern in cls.DISALLOWED_PATTERNS:
            if pattern.search(xpath):
                return False

        # Must start with // or / or (//
        if not (xpath.startswith("//") or xpath.startswith("/") or xpath.startswith("(//") or xpath.startswith("(/")):
            return False

        return True

    @classmethod
    def normalize_readability(cls, xpath: str) -> str:
        """
        Normalize XPath syntax and predicate spacing for consistent, human-readable formatting.
        """
        if not xpath:
            return ""

        s = xpath.strip()

        # Fix spacing around starts-with and contains commas e.g. starts-with(@Name,'val') -> starts-with(@Name, 'val')
        s = re.sub(r"(starts-with|contains)\((@[a-zA-Z0-9_]+),\s*([^)]+)\)", r"\1(\2, \3)", s)

        # Standardize operator spacing in compound predicates (e.g. and @ClassName -> and @ClassName)
        s = re.sub(r"\s+and\s+", " and ", s)
        s = re.sub(r"\s+or\s+", " or ", s)

        # Standardize outer index parentheses spacing e.g. ( //Window... ) [2] -> (//Window...)[2]
        s = re.sub(r"\(\s*//", "(//", s)
        s = re.sub(r"\s*\)\s*\[(\d+)\]", r")[\1]", s)

        return s
