"""
Configuration options for the xGen recorder and playback runner.
Pure Python dataclasses with zero Qt dependencies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Pattern, Sequence


@dataclass
class RedactionRule:
    """Masks sensitive text before it is recorded into a Step."""
    pattern: str                             # Regex pattern
    replacement: str = "[REDACTED]"
    scope: str = "text"                      # "text" | "name" | "all"
    action: str = "mask"                     # "mask" | "drop"
    _compiled: Optional[Pattern[str]] = field(default=None, init=False, repr=False)

    def matches(self, value: str) -> bool:
        if not self._compiled:
            self._compiled = re.compile(self.pattern, re.IGNORECASE)
        return bool(self._compiled.search(value))

    def redact(self, value: str) -> str:
        if not self._compiled:
            self._compiled = re.compile(self.pattern, re.IGNORECASE)
        return self._compiled.sub(self.replacement, value)


@dataclass
class TargetScopeOptions:
    """Limits recording to specific target applications or processes."""
    include_process_names: List[str] = field(default_factory=list)
    exclude_process_names: List[str] = field(default_factory=lambda: ["xGen", "python", "pyqt6"])
    include_pids: List[int] = field(default_factory=list)
    exclude_pids: List[int] = field(default_factory=list)
    include_window_titles_regex: List[str] = field(default_factory=list)


@dataclass
class CaptureOptions:
    """Tuning and timing options for the native capture pipeline."""
    click_debounce_ms: int = 180
    typing_debounce_ms: int = 400
    drag_threshold_px: int = 8
    max_ancestor_depth: int = 15
    native_query_deadline_ms: int = 150
    duplicate_query_deadline_ms: int = 80
    mask_password_fields: bool = True
    never_store_text: bool = False
    redaction_rules: List[RedactionRule] = field(default_factory=list)


@dataclass
class RecordingOptions:
    """Top-level options passed when starting a recording session."""
    name: str = "Recording"
    target_scope: TargetScopeOptions = field(default_factory=TargetScopeOptions)
    capture: CaptureOptions = field(default_factory=CaptureOptions)
    dialect_key: str = "windows"             # "windows" | "mac2"
    storage_dir: Optional[str] = None        # Custom output/journal path


@dataclass
class PlaybackOptions:
    """Options controlling Appium test execution driven by Action-XPath JSON."""
    explicit_wait_seconds: float = 10.0
    action_delay_seconds: float = 0.5
    continue_on_failure: bool = False
    screenshot_on_failure: bool = False
