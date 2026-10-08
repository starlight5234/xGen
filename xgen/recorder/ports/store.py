from __future__ import annotations

from typing import List, Protocol
from xgen.recorder.models import Recording, RecordingMeta, Step


class RecordingStore(Protocol):
    """
    Persistence adapter for recording sessions.
    Supports append-only journal writes during live recording and atomic finalization.
    """
    def create(self, meta: RecordingMeta) -> None:
        """Initialize storage for a new recording session."""
        ...

    def append_step(self, recording_id: str, step: Step) -> None:
        """Atomically append a recorded step to the session journal."""
        ...

    def finalize(self, recording: Recording) -> None:
        """Write final consolidated recording document."""
        ...

    def load(self, recording_id: str) -> Recording:
        """Load recording and replay its journal if final document is absent."""
        ...

    def list(self) -> List[RecordingMeta]:
        """List metadata for all persisted recordings."""
        ...

    def incomplete(self) -> List[RecordingMeta]:
        """List recordings that were started but not cleanly finalized (crash recovery)."""
        ...

    def delete(self, recording_id: str) -> None:
        """Delete a recording and its journal."""
        ...
