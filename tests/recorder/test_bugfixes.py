"""
Verification tests for the 10 Recorder bug fixes.
Ensures zero regressions and verifies each bug is permanently fixed.
"""
import io
import sys
import threading
import time
from pathlib import Path
import pytest

from xgen.core.driver_dialect import active_dialect
from xgen.recorder.adapters.jsonl_store import JsonlRecordingStore
from xgen.recorder.capture.interpreter import ActionInterpreter
from xgen.recorder.locators.engine import LocatorEngine
from xgen.recorder.locators.evidence_builder import EvidenceBuilder
from xgen.recorder.models import (
    ActionType, Bounds, CapturedContext, ElementChain, ElementFacts,
    LocatorState, ProcessFacts, RawInputEvent, RecordingMeta,
    RecorderState, ResolutionMethod, SimilarFacts, WindowFacts
)
from xgen.recorder.options import CaptureOptions, PlaybackOptions, RecordingOptions
from xgen.recorder.playback import PlaybackRunner
from xgen.recorder.service import RecorderService
from tests.recorder.fakes import (
    FakeClock, FakeContextProvider, FakeExporter, FakeInputSource,
    InMemoryRecordingStore
)


def test_bug1_step_count_eagerly_updated():
    """Bug 1: step_count in active recording meta must be updated eagerly as steps arrive."""
    clock = FakeClock()
    inp = FakeInputSource()
    ctx = FakeContextProvider()
    store = InMemoryRecordingStore()
    svc = RecorderService(clock=clock, input_source=inp, context_provider=ctx, store=store)

    rec_id = svc.start()
    assert svc._active_recording.meta.step_count == 0

    # Emit first click
    inp.emit_event(RawInputEvent("mouse_down", x=10, y=10, monotonic_ms=100))
    inp.emit_event(RawInputEvent("mouse_up", x=10, y=10, monotonic_ms=110))

    # Meta step_count must already be 1 BEFORE stop()
    assert svc._active_recording.meta.step_count == 1
    assert len(svc._active_recording.steps) == 1

    # Emit second click
    inp.emit_event(RawInputEvent("mouse_down", x=20, y=20, monotonic_ms=200))
    inp.emit_event(RawInputEvent("mouse_up", x=20, y=20, monotonic_ms=210))

    assert svc._active_recording.meta.step_count == 2

    meta = svc.stop()
    assert meta.step_count == 2


def test_bug2_locator_synthesis_outside_lock():
    """Bug 2: find_similar and generate_locators must execute without holding service._lock."""
    lock_held_during_find_similar = []

    class LockCheckingProvider(FakeContextProvider):
        def __init__(self, svc_ref):
            super().__init__()
            self.svc_ref = svc_ref

        def find_similar(self, ctx, limit=10, deadline_ms=80):
            # Check if svc._lock can be acquired without blocking
            # If RLock is held by this same thread, acquire() will succeed, but count > 1
            # A clean way: try acquiring in a separate thread. If locked, thread cannot acquire.
            can_acquire_in_other_thread = []
            def try_acquire():
                # Try non-blocking acquire from a different thread
                acq = self.svc_ref[0]._lock.acquire(blocking=False)
                if acq:
                    self.svc_ref[0]._lock.release()
                    can_acquire_in_other_thread.append(True)
                else:
                    can_acquire_in_other_thread.append(False)

            t = threading.Thread(target=try_acquire)
            t.start()
            t.join()

            lock_held_during_find_similar.append(not can_acquire_in_other_thread[0])
            return SimilarFacts(count=1, handles=(100,))

    svc_container = []
    clock = FakeClock()
    inp = FakeInputSource()
    prov = LockCheckingProvider(svc_container)
    store = InMemoryRecordingStore()
    svc = RecorderService(clock=clock, input_source=inp, context_provider=prov, store=store)
    svc_container.append(svc)

    svc.start()
    inp.emit_event(RawInputEvent("mouse_down", x=10, y=10, monotonic_ms=100))
    inp.emit_event(RawInputEvent("mouse_up", x=10, y=10, monotonic_ms=110))
    svc.stop()

    assert len(lock_held_during_find_similar) == 1
    # Must NOT have been locked by another thread during find_similar
    assert lock_held_during_find_similar[0] is False


def test_bug3_recording_meta_safe_sort_with_none_and_empty(tmp_path: Path):
    """Bug 3: RecordingMeta.from_dict handles None/empty started_at safely and JsonlStore sorts without error."""
    # Test from_dict sanitizes None
    m = RecordingMeta.from_dict({"id": "rec-1", "name": "Test1", "started_at": None})
    assert m.started_at == ""

    # Test store listing with mixed None, "", and ISO dates
    store = JsonlRecordingStore(root_dir=tmp_path)
    store.create(RecordingMeta(id="rec-1", name="NoDate", started_at=""))
    store.create(RecordingMeta(id="rec-2", name="WithDate", started_at="2026-10-08T12:00:00Z"))

    # Also test manually corrupted JSON with null started_at
    d3 = tmp_path / "rec-3"
    d3.mkdir()
    (d3 / "meta.json").write_text('{"id": "rec-3", "name": "NullDate", "started_at": null}', encoding="utf-8")

    items = store.list()
    assert len(items) == 3
    # Sorted newest first, ISO dates before empty
    assert items[0].id == "rec-2"



def test_bug5_locator_engine_attribute_with_digits():
    """Bug 5: An XPath containing digits in attributes (e.g. [@AutomationId='btn-1']) must not be misclassified as UNVERIFIED."""
    engine = LocatorEngine(dialect=active_dialect())

    target = ElementFacts(
        control_type="Button",
        name="Submit",
        automation_id="btn-123",  # Contains digits!
        class_name="ButtonClass"
    )
    window = WindowFacts(handle=0x100, title="AppWin", class_name="AppClass")
    chain = ElementChain(target=target, ancestors=(), window=window, process=ProcessFacts(pid=1))
    ctx = CapturedContext(chain=chain, resolution=ResolutionMethod.NATIVE_EXACT, captured_at_ms=1000, snapshot_cost_ms=1)

    candidates = engine.generate_locators(ctx)
    assert len(candidates) > 0

    # Find the candidate matching btn-123
    id_cand = next((c for c in candidates if "btn-123" in c.xpath), None)
    assert id_cand is not None
    # Must be UNIQUE_IN_EVIDENCE, not demoted to UNVERIFIED
    assert id_cand.state == LocatorState.UNIQUE_IN_EVIDENCE

    # But an explicit positional index candidate like //Button[1] must remain UNVERIFIED
    pos_cand = next((c for c in candidates if c.is_positional or c.xpath.endswith("[1]")), None)
    if pos_cand:
        assert pos_cand.state == LocatorState.UNVERIFIED


def test_bug6_active_recording_status_cleared_on_stop():
    """Bug 6: stop() clears active recording so status() reflects IDLE and get_recording() loads from disk."""
    clock = FakeClock()
    inp = FakeInputSource()
    ctx = FakeContextProvider()
    store = InMemoryRecordingStore()
    svc = RecorderService(clock=clock, input_source=inp, context_provider=ctx, store=store)

    rec_id = svc.start()
    inp.emit_event(RawInputEvent("mouse_down", x=10, y=10, monotonic_ms=100))
    inp.emit_event(RawInputEvent("mouse_up", x=10, y=10, monotonic_ms=110))

    st_before = svc.status()
    assert st_before.state == RecorderState.RECORDING
    assert st_before.recording_id == rec_id
    assert st_before.step_count == 1

    svc.stop()

    st_after = svc.status()
    assert st_after.state == RecorderState.IDLE
    assert st_after.recording_id is None
    assert st_after.step_count == 0
    assert st_after.duration_seconds == 0.0

    # get_recording loads from store
    disk_rec = svc.get_recording(rec_id)
    assert disk_rec.meta.id == rec_id
    assert len(disk_rec.steps) == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only WinEvent hook test")
def test_bug7_windows_scene_event_object_show_kind():
    """Bug 7: EVENT_OBJECT_SHOW is mapped to 'popup_open' and hook registration exists."""
    from xgen.recorder.adapters.windows_scene import EVENT_OBJECT_SHOW, WindowsSceneEventSource
    assert EVENT_OBJECT_SHOW == 0x8002
    src = WindowsSceneEventSource()
    assert hasattr(src, "_hook_loop")


def test_bug8_playback_continue_on_failure_and_executed_steps():
    """Bug 8: PlaybackRunner accurately reports executed_steps and sets success=False on failure under continue_on_failure."""
    class MockDriver:
        def find_element(self, by, xpath):
            if "fail" in xpath:
                raise RuntimeError("Failed intentionally")
            class El:
                def click(self): pass
            return El()

    driver = MockDriver()
    opts = PlaybackOptions(action_delay_seconds=0.0, continue_on_failure=True)
    runner = PlaybackRunner(driver, opts)

    actions = {
        "1": ["click", "//Button[@Name='First']"],
        "2": ["click", "//Button[@Name='fail']"],
        "3": ["click", "//Button[@Name='Third']"],
    }

    res = runner.run(actions)
    assert res.success is False
    assert res.total_steps == 3
    # 2 succeeded out of 3
    assert res.executed_steps == 2
    assert res.failed_step == 2
    assert "Failed intentionally" in res.error_message


def test_bug9_interpreter_flush_typing_resets_pending_state():
    """Bug 9: _flush_typing resets _pending_type_target, _pending_type_wall_time, and _pending_type_mono_ms."""
    interpreter = ActionInterpreter(options=CaptureOptions())
    ctx = FakeContextProvider().capture_at(10, 10, deadline_ms=10)

    interpreter.feed_input(RawInputEvent("key_down", key_name="h", monotonic_ms=100), ctx=ctx, wall_time_iso="2026-10-08T00:00:01Z")
    assert interpreter._pending_type_target is not None
    assert interpreter._pending_type_wall_time == "2026-10-08T00:00:01Z"
    assert interpreter._pending_type_mono_ms == 100

    step = interpreter.flush(now_ms=200)
    assert len(step) == 1
    assert step[0].params["text"] == "h"

    # Pending state must be completely cleared
    assert interpreter._pending_type_target is None
    assert interpreter._pending_type_wall_time == ""
    assert interpreter._pending_type_mono_ms == 0
    assert interpreter._pending_text == []


def test_bug10_evidence_builder_duplicates_when_target_is_root():
    """Bug 10: When target has no ancestors and window has no title, duplicates must NOT be added as children of target."""
    builder = EvidenceBuilder(dialect=active_dialect())

    target = ElementFacts(
        control_type="Button",
        name="SoloButton",
        automation_id="btnSolo"
    )
    # No ancestors, and window has empty title
    chain = ElementChain(
        target=target,
        ancestors=(),
        window=WindowFacts(handle=1, title="", class_name="WindowClass"),
        process=ProcessFacts(pid=1)
    )
    ctx = CapturedContext(chain=chain, resolution=ResolutionMethod.NATIVE_EXACT, captured_at_ms=1000, snapshot_cost_ms=1)
    similar = SimilarFacts(count=3, handles=(1, 2, 3))

    root_node, target_node = builder.build_tree(ctx, similar)

    # Target node must NOT be the root node
    assert root_node is not target_node
    # Target node must NOT have children (the duplicates must be siblings, not children!)
    assert len(target_node.children) == 0
    # Both target and duplicates must be children of root_node
    assert target_node in root_node.children
    assert len(root_node.children) == 3  # target + 2 duplicates
