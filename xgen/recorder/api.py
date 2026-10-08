"""
xGen Recorder — Public API Contract.
The single surface exposed to all clients (Qt GUI, CLI, MCP Server).
Pure Python interfaces and exceptions. Zero Qt dependencies.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable, List, Mapping, Optional, Protocol

from xgen.recorder.models import (
    ExportResult, ExporterInfo, PagedSteps, Recording, RecordingMeta,
    RecordingStatus, Step
)
from xgen.recorder.options import RecordingOptions


class RecorderErrorCode(str, Enum):
    INVALID_STATE = "invalid_state"
    RECORDING_NOT_FOUND = "recording_not_found"
    STEP_NOT_FOUND = "step_not_found"
    EXPORTER_NOT_FOUND = "exporter_not_found"
    PERMISSION_DENIED = "permission_denied"
    HOOK_FAILED = "hook_failed"
    EXPORT_FAILED = "export_failed"
    INVALID_ARGUMENT = "invalid_argument"


class RecorderError(Exception):
    """Domain exception raised by RecorderApi operations."""
    def __init__(self, code: RecorderErrorCode, message: str, details: Optional[Mapping[str, Any]] = None):
        super().__init__(f"[{code.value}] {message}")
        self.code = code
        self.message = message
        self.details = details or {}


class RecorderApi(Protocol):
    """
    Public contract for recording, inspecting, editing, and exporting desktop actions.
    """
    # Lifecycle
    def start(self, options: Optional[RecordingOptions] = None) -> str:
        """Begin a new recording session. Returns unique recording_id."""
        ...

    def pause(self) -> None:
        """Temporarily pause recording without terminating the session."""
        ...

    def resume(self) -> None:
        """Resume recording after being paused."""
        ...

    def stop(self) -> RecordingMeta:
        """End the recording session, flush journal, and finalize document."""
        ...

    def status(self) -> RecordingStatus:
        """Retrieve current recorder state, step count, and active window info."""
        ...

    # Steps & Timeline
    def get_steps(self, since_seq: int = 0, limit: int = 100) -> PagedSteps:
        """Retrieve paginated steps recorded in the active or most recent session."""
        ...

    def get_step(self, step_id: str) -> Step:
        """Retrieve a specific step by its unique ID."""
        ...

    def update_step(self, step_id: str, patch: Mapping[str, Any]) -> Step:
        """Update mutable fields of a recorded step (notes, params, locators)."""
        ...

    def delete_step(self, step_id: str) -> bool:
        """Remove a step from the recording sequence."""
        ...

    def restore_step(self, step: Step, index: Optional[int] = None) -> bool:
        """Restore a previously deleted step back into the recording sequence."""
        ...

    def clear_steps(self) -> bool:
        """Clear all steps from the active or most recent recording session."""
        ...

    def select_locator(self, step_id: str, locator_index: int) -> Step:
        """Set the active locator candidate index for the step."""
        ...

    # Inspection
    def inspect_at_cursor(self) -> Optional[Step]:
        """Perform a one-off capture of the element under cursor without advancing sequence."""
        ...

    # Storage & History
    def get_recording(self, recording_id: str) -> Recording:
        """Load a complete persisted recording."""
        ...

    def list_recordings(self) -> List[RecordingMeta]:
        """List all saved recordings."""
        ...

    def list_incomplete_recordings(self) -> List[RecordingMeta]:
        """List unfinalized recordings for crash recovery."""
        ...

    def delete_recording(self, recording_id: str) -> None:
        """Delete a saved recording."""
        ...

    # Exporters & Output
    def list_exporters(self) -> List[ExporterInfo]:
        """List all available exporters (action_xpath_json, pytest_appium, raw_json)."""
        ...

    def export(self, recording_id: str, exporter_id: str = "action_xpath_json",
               options: Optional[Mapping[str, Any]] = None) -> ExportResult:
        """Export recording into the requested format."""
        ...

    # Verification
    def start_verification(self, recording_id: str, driver: Any = None) -> str:
        """Start an asynchronous verification job to test recorded locators against Appium."""
        ...

    def get_verification_job(self, job_id: str) -> Optional[Any]:
        """Query progress and results of a verification job."""
        ...

    def cancel_verification_job(self, job_id: str) -> bool:
        """Cancel a running verification job."""
        ...

    # Streaming notifications
    def subscribe(self, listener: Callable[[Any], None]) -> Callable[[], None]:
        """Subscribe to live recorder events. Returns unsubscribe callable."""
        ...
