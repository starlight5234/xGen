"""
Verification tests for the 7 second-sweep Recorder bug fixes.
Ensures zero regressions and verifies each second-sweep bug is permanently resolved.
"""
from __future__ import annotations

import io
import sys
import threading
from typing import Any, Mapping
from unittest.mock import MagicMock, patch
import pytest

from xgen.recorder.api import RecorderError, RecorderErrorCode
from xgen.recorder.models import (
    ActionType, CapturedContext, ElementChain, ElementFacts,
    LocatorState, ProcessFacts, RawInputEvent, RecorderState,
    ResolutionMethod, SceneEvent, SceneSnapshotFacts, WindowFacts
)
from xgen.recorder.options import (
    CaptureOptions, PlaybackOptions, RecordingOptions, TargetScopeOptions
)
from xgen.recorder.playback import PlaybackRunner
from xgen.recorder.service import RecorderService
from xgen.recorder.verification import (
    VerificationJob, VerificationReport, VerificationRunner
)
from xgen.recorder.adapters.windows_scene import (
    EVENT_OBJECT_SHOW, EVENT_SYSTEM_MENUPOPUPSTART, WindowsSceneEventSource
)
from tests.recorder.fakes import (
    FakeClock, FakeContextProvider, FakeInputSource, InMemoryRecordingStore
)


# -----------------------------------------------------------------------------
# Bug 2 Tests
# -----------------------------------------------------------------------------

def test_sweep2_bug2_scope_allowed_none_process_names():
    """Bug 2: _is_scope_allowed must not crash with AttributeError when process names are None."""
    svc = RecorderService(
        clock=FakeClock(),
        input_source=FakeInputSource(),
        context_provider=FakeContextProvider(),
        store=InMemoryRecordingStore()
    )
    opts = RecordingOptions(
        target_scope=TargetScopeOptions(
            include_process_names=["notepad.exe", "calc.exe"]
        )
    )
    svc.start(opts)

    # Context with None exe_name and app_name
    chain = ElementChain(
        target=ElementFacts(control_type="Button", name="OK"),
        ancestors=(),
        window=WindowFacts(handle=100, title="Test Window", class_name="WindowClass"),
        process=ProcessFacts(pid=1234, exe_name=None, app_name=None)
    )
    ctx = CapturedContext(
        chain=chain,
        resolution=ResolutionMethod.NATIVE_EXACT,
        captured_at_ms=100,
        snapshot_cost_ms=1
    )

    # Must safely return False without raising AttributeError
    allowed = svc._is_scope_allowed(ctx)
    assert allowed is False

    # When matching process name is present, should return True
    chain_matching = ElementChain(
        target=ElementFacts(control_type="Button", name="OK"),
        ancestors=(),
        window=WindowFacts(handle=100, title="Test Window", class_name="WindowClass"),
        process=ProcessFacts(pid=1234, exe_name="notepad.exe", app_name="Notepad")
    )
    ctx_matching = CapturedContext(
        chain=chain_matching,
        resolution=ResolutionMethod.NATIVE_EXACT,
        captured_at_ms=100,
        snapshot_cost_ms=1
    )
    assert svc._is_scope_allowed(ctx_matching) is True
    svc.stop()


# -----------------------------------------------------------------------------
# Bug 3 Tests
# -----------------------------------------------------------------------------

def test_sweep2_bug3_scene_snapshot_outside_lock():
    """Bug 3: _on_scene_event must call scene_source.snapshot without holding service._lock."""
    lock_held_during_snapshot = []

    class FakeSceneSource:
        def __init__(self, svc_container):
            self.svc_container = svc_container
            self.sink = None

        def start(self, sink):
            self.sink = sink

        def stop(self):
            self.sink = None

        def snapshot(self, window_handle, deadline_ms=200):
            can_acquire = []
            def try_acquire():
                acq = self.svc_container[0]._lock.acquire(blocking=False)
                if acq:
                    self.svc_container[0]._lock.release()
                    can_acquire.append(True)
                else:
                    can_acquire.append(False)

            t = threading.Thread(target=try_acquire)
            t.start()
            t.join()

            lock_held_during_snapshot.append(not can_acquire[0])
            return SceneSnapshotFacts(
                window=WindowFacts(handle=window_handle, title="Popup", class_name="PopupClass"),
                elements=(),
                captured_at_ms=100
            )

    svc_container = []
    source = FakeSceneSource(svc_container)
    svc = RecorderService(
        clock=FakeClock(),
        input_source=FakeInputSource(),
        context_provider=FakeContextProvider(),
        store=InMemoryRecordingStore(),
        scene_source=source
    )
    svc_container.append(svc)

    svc.start()
    svc._on_scene_event(SceneEvent(kind="popup_open", window_handle=999, monotonic_ms=100))
    svc.stop()

    assert len(lock_held_during_snapshot) == 1
    # Must NOT have been locked by another thread during snapshot()
    assert lock_held_during_snapshot[0] is False


# -----------------------------------------------------------------------------
# Bug 4 Tests
# -----------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only WinEvent hook test")
def test_sweep2_bug4_windows_scene_filters_child_event_object_show():
    """Bug 4: win_event_callback must ignore EVENT_OBJECT_SHOW if hwnd has a parent window."""
    events_received = []
    source = WindowsSceneEventSource()
    source.start(lambda ev: events_received.append(ev))

    # Retrieve callback
    cb = source._hook_fn

    def set_buf_text(h, buf, l):
        buf.value = "TopWindow"
        return len("TopWindow")

    with patch("xgen.recorder.adapters.windows_scene.user32") as mock_user32:
        # 1. Child control has parent -> user32.GetParent returns 0x1234
        mock_user32.GetParent.return_value = 0x1234
        mock_user32.GetWindowTextLengthW.return_value = 9
        mock_user32.GetWindowTextW.side_effect = set_buf_text

        cb(1, EVENT_OBJECT_SHOW, 0x5678, 0, 0, 0, 100)
        assert len(events_received) == 0  # Ignored!

        # 2. Top-level popup -> user32.GetParent returns 0
        mock_user32.GetParent.return_value = 0
        cb(1, EVENT_OBJECT_SHOW, 0x9999, 0, 0, 0, 200)
        assert len(events_received) == 1
        assert events_received[0].kind == "popup_open"
        assert events_received[0].window_handle == 0x9999
        assert events_received[0].title == "TopWindow"

    source.stop()


# -----------------------------------------------------------------------------
# Bug 5 Tests
# -----------------------------------------------------------------------------

def test_sweep2_bug5_get_recording_raises_recording_not_found():
    """Bug 5: service.get_recording and export must raise RecorderError(RECORDING_NOT_FOUND) on missing ID."""
    svc = RecorderService(
        clock=FakeClock(),
        input_source=FakeInputSource(),
        context_provider=FakeContextProvider(),
        store=InMemoryRecordingStore()
    )

    with pytest.raises(RecorderError) as exc_info:
        svc.get_recording("non-existent-rec-id")

    assert exc_info.value.code == RecorderErrorCode.RECORDING_NOT_FOUND
    assert "non-existent-rec-id" in exc_info.value.message

    with pytest.raises(RecorderError) as exc_export:
        svc.export("non-existent-rec-id")

    assert exc_export.value.code == RecorderErrorCode.RECORDING_NOT_FOUND


# -----------------------------------------------------------------------------
# Bug 6 Tests
# -----------------------------------------------------------------------------

def test_sweep2_bug6_verification_cancellation_race_condition():
    """Bug 6: VerificationRunner must not overwrite cancelled status with completed."""
    runner = VerificationRunner()

    from xgen.recorder.models import LocatorCandidate, Recording, RecordingMeta, Step
    rec = Recording(
        meta=RecordingMeta(id="rec-test", name="Test"),
        steps=[
            Step(
                id="s1",
                seq=1,
                action=ActionType.CLICK,
                created_at="2026-10-08T00:00:00Z",
                monotonic_ms=100,
                process=ProcessFacts(pid=1),
                window=WindowFacts(handle=1, title="Test", class_name="TestClass"),
                locators=[LocatorCandidate(xpath="//Button[@Name='Test']", tier="direct")]
            )
        ]
    )

    job = VerificationJob(id="job-1", recording_id="rec-test", total_steps=1)

    # Simulate cancellation occurring right before loop completes
    class FakeDriver:
        def find_elements(self, *args, **kwargs):
            job._cancelled = True
            job.status = "cancelled"
            return []

    runner._run_job(job, rec, FakeDriver())

    # Final status must remain "cancelled" and report must NOT be finalized as completed
    assert job.status == "cancelled"
    assert job.report is None


# -----------------------------------------------------------------------------
# Bug 7 Tests
# -----------------------------------------------------------------------------

def test_sweep2_bug7_playback_executed_steps_accurate_count():
    """Bug 7: PlaybackRunner must accurately report executed_count when steps are skipped or empty."""
    class FakeDriver:
        def __init__(self):
            self.clicks = 0

        def find_element(self, by, value):
            fake_el = MagicMock()
            fake_el.click.side_effect = lambda: setattr(self, "clicks", self.clicks + 1)
            return fake_el

    driver = FakeDriver()
    opts = PlaybackOptions(action_delay_seconds=0.0)
    runner = PlaybackRunner(driver, opts)

    # 3 items, but middle item is empty (skipped)
    actions = {
        "1": ["click", "//Button[@Name='First']"],
        "2": [],
        "3": ["click", "//Button[@Name='Third']"],
    }

    result = runner.run(actions)
    assert result.success is True
    assert result.total_steps == 3
    # executed_steps must be 2, NOT 3!
    assert result.executed_steps == 2
    assert driver.clicks == 2
