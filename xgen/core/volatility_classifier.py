"""
Volatility-Aware Attribute Classifier for xGen v3.
Evaluates whether AutomationIds, Names, and substrings are machine-generated,
session-scoped, counter-driven, or durable for production test automation.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from enum import Enum
from typing import List, Optional


class VolatilityVerdict(Enum):
    STATIC = "STATIC"       # Clean, human/developer-defined durable ID (100 pts)
    SUSPECT = "SUSPECT"     # Looks auto-generated/hash-suffixed; capped at 55 pts (Moderate)
    VOLATILE = "VOLATILE"   # Transient / session-scoped; excluded from ID generation


class NumericContext(Enum):
    ORDINAL_LABEL = "ORDINAL_LABEL"     # "Page 2", "Tab 1" -> 70 pts (85 scoped)
    UNKNOWN_NUMERIC = "UNKNOWN_NUMERIC" # Standard text with numbers -> 60 pts (70 scoped)
    COUNTER = "COUNTER"                 # "47 of 312" -> 35 pts
    TIMESTAMP = "TIMESTAMP"             # "12:30:00" -> 35 pts
    LIVE_VALUE = "LIVE_VALUE"           # "$19.99" -> 35 pts


class VolatilityClassifier:
    """Classifies identifier and name volatility using structural heuristics and entropy."""

    GUID_PATTERN = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )
    HEX_RUN_PATTERN = re.compile(r"^[0-9a-fA-F]{6,}$")
    REACT_USE_ID_PATTERN = re.compile(r"^:r[0-9a-z]+:$", re.IGNORECASE)
    FRAMEWORK_AUTO_ID_PATTERN = re.compile(r"^(id|el|item|node|ctl|ctrl|view)[-_]?\d{3,}$", re.IGNORECASE)
    COMPOSITE_HASH_SUFFIX = re.compile(r"^\w+[-_][0-9a-fA-F]{6,}$")

    # Numeric context patterns
    COUNTER_PATTERN = re.compile(r"\b\d{1,3}\s+of\s+\d{1,4}\b", re.IGNORECASE)
    TIMESTAMP_PATTERN = re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b")
    LIVE_VALUE_PATTERN = re.compile(r"[\$€£¥₹]?\s*\d+[.,]\d{2}\b")
    ORDINAL_PATTERN = re.compile(r"^(Tab|Page|Step|Document|Sheet|Section|Item|Window)\s+\d{1,2}$", re.IGNORECASE)

    @classmethod
    def is_pure_integer(cls, val: str) -> bool:
        """Check if string is purely numeric."""
        return val.strip().isdigit()

    @classmethod
    def is_guid_pattern(cls, val: str) -> bool:
        """Check if string matches standard UUID/GUID pattern."""
        return bool(cls.GUID_PATTERN.match(val.strip()))

    @classmethod
    def has_high_char_entropy(cls, val: str, threshold: float = 3.8) -> bool:
        """
        Calculate Shannon character entropy of the string.
        High entropy indicates random hashes, base64 tokens, or machine-generated IDs.
        """
        s = val.strip()
        if len(s) < 8:
            return False

        freqs = Counter(s)
        total = len(s)
        entropy = -sum((count / total) * math.log2(count / total) for count in freqs.values())
        return entropy >= threshold

    @classmethod
    def classify_id_volatility(cls, val: str) -> VolatilityVerdict:
        """
        Classifies an AutomationId or ClassName string.
        Returns VolatilityVerdict.STATIC, SUSPECT, or VOLATILE.
        """
        if not val or not val.strip():
            return VolatilityVerdict.VOLATILE

        s = val.strip()

        # Check pure integer
        if cls.is_pure_integer(s):
            return VolatilityVerdict.VOLATILE

        # Check React useId
        if cls.REACT_USE_ID_PATTERN.match(s):
            return VolatilityVerdict.VOLATILE

        # Check framework auto ID (e.g. el_183920, ctl00_12)
        if cls.FRAMEWORK_AUTO_ID_PATTERN.match(s):
            return VolatilityVerdict.VOLATILE

        # Check GUID
        if cls.is_guid_pattern(s):
            return VolatilityVerdict.SUSPECT

        # Check bare hex/hash
        if cls.HEX_RUN_PATTERN.match(s) and len(s) >= 8:
            return VolatilityVerdict.VOLATILE

        # Check composite with hash suffix
        if cls.COMPOSITE_HASH_SUFFIX.match(s):
            return VolatilityVerdict.SUSPECT

        # Check character entropy
        if cls.has_high_char_entropy(s, threshold=3.8):
            return VolatilityVerdict.SUSPECT

        return VolatilityVerdict.STATIC

    @classmethod
    def classify_numeric_name(cls, name: str) -> NumericContext:
        """
        Distinguish stable ordinal labels from dynamic counters, timestamps, or live values.
        """
        if not name or not name.strip():
            return NumericContext.UNKNOWN_NUMERIC

        s = name.strip()

        if cls.COUNTER_PATTERN.search(s):
            return NumericContext.COUNTER
        if cls.TIMESTAMP_PATTERN.search(s):
            return NumericContext.TIMESTAMP
        if cls.LIVE_VALUE_PATTERN.search(s):
            return NumericContext.LIVE_VALUE
        if cls.ORDINAL_PATTERN.match(s):
            return NumericContext.ORDINAL_LABEL
        if any(ch.isdigit() for ch in s):
            return NumericContext.UNKNOWN_NUMERIC

        return NumericContext.ORDINAL_LABEL

    @classmethod
    def extract_stable_substring(cls, name: str) -> Optional[str]:
        """
        Extract a clean, non-volatile prefix/substring from a name.
        Validates that extracted substring does not contain dynamic counters or high entropy fragments.
        """
        if not name or len(name.strip()) < 3:
            return None

        TRIVIAL_TOKENS = {"ok", "no", "yes", "on", "off", "new", "all", "any", "add", "the", "a", "an"}

        # Strategy 1: Delimiter split (e.g. "xGen - Antigravity IDE - Review" -> "xGen", "MINGW64:/e/..." -> "MINGW64")
        for delim in [" - ", ":", " | ", " — "]:
            if delim in name:
                prefix = name.split(delim)[0].strip()
                if 3 <= len(prefix) < len(name) and prefix.lower() not in TRIVIAL_TOKENS:
                    ctx = cls.classify_numeric_name(prefix)
                    if ctx not in (NumericContext.COUNTER, NumericContext.TIMESTAMP, NumericContext.LIVE_VALUE):
                        if not cls.has_high_char_entropy(prefix, threshold=3.8):
                            return prefix

        # Strategy 2: Clean substring of reasonably long titles (snapping to word boundaries)
        clean = name.strip()
        if len(clean) >= 6:
            tok = clean[:24]
            boundary = tok.rfind(" ")
            if boundary >= 3:
                tok = tok[:boundary].strip()
            else:
                tok = tok.strip()

            if len(tok) >= 4 and tok != clean and tok.lower() not in TRIVIAL_TOKENS:
                ctx = cls.classify_numeric_name(tok)
                if ctx not in (NumericContext.COUNTER, NumericContext.TIMESTAMP, NumericContext.LIVE_VALUE):
                    if not cls.has_high_char_entropy(tok, threshold=3.8):
                        return tok

        return None
