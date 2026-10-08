"""
UI Tests for Recorder Qt Transport (Bridge, Controls, Panel).
Uses Fake/In-Memory RecorderApi to verify UI event handling and user interactions.
"""
import sys
from pathlib import Path
import pytest
from PyQt6.QtWidgets import QApplication

from tests.recorder.fakes import (
    FakeClock, FakeContextProvider, FakeExporter, FakeInputSource,
    InMemoryRecordingStore
)
from xgen.recorder.events import (
    EventBus, StateChangedEvent, StepRecordedEvent, StepUpdatedEvent,
    StepDeletedEvent
)
from xgen.recorder.models import (
    ActionType, LocatorCandidate, LocatorState, ProcessFacts, RawInputEvent,
    RecorderState, Step, WindowFacts
)
from xgen.recorder.service import RecorderService
from xgen.ui.recorder.bridge import RecorderQtBridge
from xgen.ui.recorder.controls import RecorderControls
from xgen.ui.recorder.panel import RecorderPanel


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def fake_service():
    clock = FakeClock()
    input_source = FakeInputSource()
    ctx_provider = FakeContextProvider()
    store = InMemoryRecordingStore()
    exporter = FakeExporter()
    bus = EventBus()

    svc = RecorderService(
        clock=clock,
        input_source=input_source,
        context_provider=ctx_provider,
        store=store,
        exporters={"action_xpath_json": exporter},
        event_bus=bus
    )
    return svc, bus


def test_recorder_qt_bridge_signals(qapp, fake_service):
    svc, bus = fake_service
    bridge = RecorderQtBridge(svc)

    state_changes = []
    steps_added = []
    steps_updated = []
    steps_removed = []

    bridge.state_changed.connect(lambda s: state_changes.append(s))
    bridge.step_added.connect(lambda s: steps_added.append(s))
    bridge.step_updated.connect(lambda s: steps_updated.append(s))
    bridge.step_removed.connect(lambda s_id: steps_removed.append(s_id))

    # Publish events directly onto the bus
    bus.publish(StateChangedEvent(old_state=RecorderState.IDLE, new_state=RecorderState.RECORDING, recording_id="rec-1"))
    
    step = Step(
        id="step-1", seq=1, action=ActionType.CLICK, created_at="2026-10-07T12:00:00Z", monotonic_ms=100,
        process=ProcessFacts(pid=1), window=WindowFacts(handle=1, title="Test", class_name="Wnd")
    )
    bus.publish(StepRecordedEvent(recording_id="rec-1", step=step))

    step.notes = "Updated notes"
    bus.publish(StepUpdatedEvent(recording_id="rec-1", step=step))
    bus.publish(StepDeletedEvent(recording_id="rec-1", step_id="step-1"))

    # Process pending Qt events
    QApplication.processEvents()

    assert state_changes == ["recording"]
    assert len(steps_added) == 1
    assert steps_added[0].id == "step-1"
    assert len(steps_updated) == 1
    assert steps_updated[0].notes == "Updated notes"
    assert steps_removed == ["step-1"]

    bridge.dispose()


def test_recorder_controls_state_transitions(qapp):
    controls = RecorderControls()

    assert controls._current_state == "idle"
    assert controls.btn_record.isEnabled()
    assert not controls.btn_pause.isEnabled()
    assert not controls.btn_stop.isEnabled()

    # Transition to recording
    controls.set_state("recording", duration_sec=5.0, step_count=2)
    assert controls._current_state == "recording"
    assert controls.btn_pause.isEnabled()
    assert controls.btn_stop.isEnabled()
    assert "REC" in controls.lbl_status.text()

    # Transition to paused
    controls.set_state("paused", duration_sec=10.0, step_count=3)
    assert controls._current_state == "paused"
    assert "PAUSED" in controls.lbl_status.text()

    # Stop back to idle
    controls.set_state("idle")
    assert controls._current_state == "idle"
    assert not controls.btn_pause.isEnabled()


def test_recorder_panel_timeline_and_selection(qapp, fake_service):
    svc, bus = fake_service
    bridge = RecorderQtBridge(svc)
    panel = RecorderPanel(svc, bridge)

    # 1. Add step via bridge
    step = Step(
        id="s10", seq=1, action=ActionType.CLICK, created_at="2026-10-07T12:00:00Z", monotonic_ms=1000,
        process=ProcessFacts(pid=200, exe_name="notepad.exe"),
        window=WindowFacts(handle=10, title="Notepad", class_name="Notepad"),
        locators=[
            LocatorCandidate(xpath="//Button[@Name='File']", tier="1", stability_score=90, state=LocatorState.UNIQUE_IN_EVIDENCE),
            LocatorCandidate(xpath="//MenuItem[1]", tier="2", stability_score=40, state=LocatorState.AMBIGUOUS)
        ],
        selected_locator=0
    )
    bridge.step_added.emit(step)
    QApplication.processEvents()

    assert panel.step_list.count() == 1

    # 2. Select step in list
    panel.step_list.setCurrentRow(0)
    QApplication.processEvents()

    assert panel._current_step_id == "s10"
    assert "CLICK" in panel.lbl_step_info.text()
    assert "Notepad" in panel.lbl_step_info.text()
    assert panel.combo_locators.count() == 2
    assert "UNIQUE_IN_EVIDENCE" in panel.lbl_locator_state.text()

    bridge.dispose()


def test_main_window_recorder_start_deactivates_inspect_mode(qapp):
    """Verify MainWindow._on_recorder_start safely inspects is_active property and deactivates inspect mode."""
    from unittest.mock import patch
    from xgen.config import XGenConfig
    from xgen.ui.main_window import MainWindow
    from xgen.ui.recorder.completion_dialog import RecordingCompletionDialog

    cfg = XGenConfig(auto_connect_on_startup=False, pin_on_top=False)
    win = MainWindow(cfg, start_hooks=False)

    try:
        # Activate inspect mode
        win.inspect_mode.activate()
        assert win.inspect_mode.is_active is True

        # Call _on_recorder_start with mocked recorder service start to prevent OS hook block in headless environment
        with patch.object(win.recorder_service, "start"), \
             patch.object(win.recorder_service, "stop", return_value=win.recorder_service.status()):
            win._on_recorder_start()

            # Inspect mode must be deactivated and inspect button unchecked
            assert win.inspect_mode.is_active is False
            assert win.toolbar.btn_inspect.isChecked() is False

            with patch.object(RecordingCompletionDialog, "exec"):
                win._on_recorder_stop()
    finally:
        win.close()


def test_floating_recorder_overlay_states_and_signals(qapp):
    """Verify FloatingRecorderOverlay updates timer, step badge, and emits control signals."""
    from xgen.ui.recorder.floating_overlay import FloatingRecorderOverlay

    overlay = FloatingRecorderOverlay()
    assert overlay._is_paused is False

    # Check step count update
    overlay.set_step_count(7)
    assert overlay.lbl_steps.text() == "7 steps"

    # Check pause toggle
    overlay.set_paused(True)
    assert overlay._is_paused is True
    assert "PAUSED" in overlay.lbl_timer.text()
    assert overlay.btn_pause.text() == "▶ Resume"

    overlay.set_paused(False)
    assert overlay._is_paused is False
    assert "REC" in overlay.lbl_timer.text()
    assert overlay.btn_pause.text() == "⏸ Pause"

    # Check stop signal emission
    stops = []
    overlay.stop_requested.connect(lambda: stops.append(True))
    overlay.btn_stop.click()
    assert stops == [True]

    overlay.close()


def test_recording_completion_dialog_ui(qapp, tmp_path):
    """Verify RecordingCompletionDialog displays session stats and correct explorer path."""
    from pathlib import Path
    from xgen.recorder.models import RecordingMeta
    from xgen.ui.recorder.completion_dialog import RecordingCompletionDialog

    meta = RecordingMeta(
        id="rec-demo-123",
        name="Flow Demo",
        started_at="2026-10-08T00:00:00Z",
        step_count=8,
        duration_seconds=12.5
    )

    test_storage = tmp_path / "test_recordings"
    test_storage.mkdir(parents=True, exist_ok=True)
    fake_svc = None
    dlg = RecordingCompletionDialog(meta, test_storage, fake_svc)

    assert "rec-demo-123" in str(dlg.storage_dir)
    assert dlg.meta.name == "Flow Demo"
    dlg.close()

