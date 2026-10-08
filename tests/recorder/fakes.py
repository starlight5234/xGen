"""
Test Fakes and In-Memory Test Adapters for Recorder Ports.
Enables testing the entire recorder core without OS hooks or file I/O.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from xgen.recorder.models import (
    Bounds, CapturedContext, ContextCapabilities, ElementChain, ElementFacts,
    ExportResult, ProcessFacts, RawInputEvent, Recording, RecordingMeta,
    ResolutionMethod, SceneEvent, SceneSnapshotFacts, SimilarFacts, Step,
    WindowFacts
)
from xgen.recorder.ports.clock import Clock
from xgen.recorder.ports.context import NativeContextProvider
from xgen.recorder.ports.exporter import Exporter
from xgen.recorder.ports.input_source import InputSource
from xgen.recorder.ports.scene import SceneEventSource
from xgen.recorder.ports.store import RecordingStore


class FakeClock:
    def __init__(self, start_mono_ms: int = 1000, start_iso: str = "2026-10-07T12:00:00Z"):
        self._mono_ms = start_mono_ms
        self._iso = start_iso

    def monotonic_ms(self) -> int:
        return self._mono_ms

    def wall_time_iso(self) -> str:
        return self._iso

    def advance_ms(self, delta_ms: int) -> None:
        self._mono_ms += delta_ms


class FakeInputSource:
    def __init__(self):
        self._sink: Optional[Callable[[RawInputEvent], None]] = None
        self._running = False

    def start(self, sink: Callable[[RawInputEvent], None]) -> None:
        self._sink = sink
        self._running = True

    def stop(self) -> None:
        self._running = False
        self._sink = None

    def is_running(self) -> bool:
        return self._running

    def emit_event(self, event: RawInputEvent) -> None:
        if self._running and self._sink:
            self._sink(event)


class FakeContextProvider:
    def __init__(self):
        self._cursor = (100, 200)
        self._context_map: Dict[Tuple[int, int], CapturedContext] = {}
        self._focused_context: Optional[CapturedContext] = None

    def capabilities(self) -> ContextCapabilities:
        return ContextCapabilities()

    def cursor_position(self) -> Tuple[int, int]:
        return self._cursor

    def set_cursor(self, x: int, y: int) -> None:
        self._cursor = (x, y)

    def set_context_at(self, x: int, y: int, ctx: CapturedContext) -> None:
        self._context_map[(x, y)] = ctx

    def set_focused_context(self, ctx: CapturedContext) -> None:
        self._focused_context = ctx

    def capture_at(self, x: int, y: int, *, deadline_ms: int) -> Optional[CapturedContext]:
        if (x, y) in self._context_map:
            return self._context_map[(x, y)]
        # Default fallback context
        target = ElementFacts(control_type="Button", name="Submit", automation_id="btnSubmit")
        window = WindowFacts(handle=0x1000, title="TestApp", class_name="QtWindow")
        process = ProcessFacts(pid=1234, exe_name="app.exe")
        chain = ElementChain(target=target, ancestors=(), window=window, process=process)
        return CapturedContext(chain=chain, resolution=ResolutionMethod.NATIVE_EXACT, captured_at_ms=1000, snapshot_cost_ms=2)

    def capture_focused(self, *, deadline_ms: int) -> Optional[CapturedContext]:
        if self._focused_context:
            return self._focused_context
        target = ElementFacts(control_type="Edit", name="Username", automation_id="txtUser")
        window = WindowFacts(handle=0x1000, title="TestApp", class_name="QtWindow")
        process = ProcessFacts(pid=1234, exe_name="app.exe")
        chain = ElementChain(target=target, ancestors=(), window=window, process=process)
        return CapturedContext(chain=chain, resolution=ResolutionMethod.NATIVE_EXACT, captured_at_ms=1000, snapshot_cost_ms=2)

    def find_similar(self, ctx: CapturedContext, *, limit: int, deadline_ms: int) -> SimilarFacts:
        return SimilarFacts(count=1, handles=(ctx.chain.target.native_handle,))

    def window_still_exists(self, window_handle: int) -> bool:
        return True

    def same_title_windows(self, window: WindowFacts) -> int:
        return 1

    def process_of_point(self, x: int, y: int) -> Optional[int]:
        return 1234


class InMemoryRecordingStore:
    def __init__(self):
        self.recordings: Dict[str, Recording] = {}
        self.journals: Dict[str, List[Step]] = {}

    def create(self, meta: RecordingMeta) -> None:
        self.recordings[meta.id] = Recording(meta=meta, steps=[])
        self.journals[meta.id] = []

    def append_step(self, recording_id: str, step: Step) -> None:
        if recording_id in self.journals:
            self.journals[recording_id].append(step)

    def finalize(self, recording: Recording) -> None:
        self.recordings[recording.meta.id] = recording

    def load(self, recording_id: str) -> Recording:
        if recording_id not in self.recordings:
            raise KeyError(f"Recording {recording_id} not found")
        rec = self.recordings[recording_id]
        if not rec.steps and recording_id in self.journals:
            rec.steps = list(self.journals[recording_id])
        return rec

    def list(self) -> List[RecordingMeta]:
        return [r.meta for r in self.recordings.values()]

    def incomplete(self) -> List[RecordingMeta]:
        return [r.meta for r in self.recordings.values() if r.meta.id in self.journals and not r.meta.stopped_at]

    def delete(self, recording_id: str) -> None:
        self.recordings.pop(recording_id, None)
        self.journals.pop(recording_id, None)


class FakeExporter:
    def __init__(self, exporter_id: str = "action_xpath_json", extension: str = "json"):
        self.id = exporter_id
        self.display_name = "Action XPath JSON Exporter"
        self.file_extension = extension

    def option_schema(self) -> Mapping[str, Any]:
        return {"indent": {"type": "integer", "default": 2}}

    def export(self, recording: Recording, options: Mapping[str, Any]) -> ExportResult:
        import json
        actions_map = {str(s.seq): s.to_action_array() for s in recording.steps}
        text = json.dumps(actions_map, indent=2)
        return ExportResult(text=text, filename=f"{recording.meta.name}.json", stats={"step_count": len(recording.steps)})


class FakeSceneEventSource:
    def __init__(self):
        self._sink: Optional[Callable[[SceneEvent], None]] = None
        self._snapshots: Dict[int, SceneSnapshotFacts] = {}
        self._running = False

    def start(self, sink: Callable[[SceneEvent], None]) -> None:
        self._sink = sink
        self._running = True

    def stop(self) -> None:
        self._running = False
        self._sink = None

    def is_running(self) -> bool:
        return self._running

    def set_snapshot(self, window_handle: int, snapshot: SceneSnapshotFacts) -> None:
        self._snapshots[window_handle] = snapshot

    def snapshot(self, window_handle: int, *, deadline_ms: int = 200) -> Optional[SceneSnapshotFacts]:
        return self._snapshots.get(window_handle)

    def emit_event(self, event: SceneEvent) -> None:
        if self._running and self._sink:
            self._sink(event)

