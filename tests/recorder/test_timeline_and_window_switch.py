"""
Unit tests for Recorder Timeline Dialog, session clearing, and window switch behavior.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from xgen.recorder.models import (
    ActionType, LocatorCandidate, LocatorState, ProcessFacts, Recording,
    RecordingMeta, Step, WindowFacts
)
from xgen.ui.recorder.bridge import RecorderQtBridge
from xgen.ui.recorder.panel import RecorderPanel
from xgen.ui.recorder.timeline_dialog import RecorderTimelineDialog
import sys
from tests.recorder.fakes import (
    FakeClock, FakeContextProvider, FakeExporter, FakeInputSource,
    InMemoryRecordingStore
)
from xgen.recorder.events import EventBus
from xgen.recorder.service import RecorderService

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

def test_timeline_dialog_and_panel_session_clearing(qapp, fake_service):
    svc, bus = fake_service
    bridge = RecorderQtBridge(svc)

    dlg = RecorderTimelineDialog(svc, bridge)
    panel = dlg.panel

    # Session 1 steps
    step1 = Step(
        id="s1", seq=1, action=ActionType.CLICK, created_at="2026-10-08T00:00:00Z", monotonic_ms=100,
        process=ProcessFacts(pid=100, exe_name="explorer.exe"),
        window=WindowFacts(handle=1, title="Explorer", class_name="CabinetWClass")
    )
    step2 = Step(
        id="s2", seq=2, action=ActionType.CLICK, created_at="2026-10-08T00:00:01Z", monotonic_ms=200,
        process=ProcessFacts(pid=100, exe_name="explorer.exe"),
        window=WindowFacts(handle=1, title="Explorer", class_name="CabinetWClass")
    )
    bridge.step_added.emit(step1)
    bridge.step_added.emit(step2)
    QApplication.processEvents()

    assert len(panel._steps) == 2
    assert panel.step_list.count() == 2

    # When a new recording starts, state becomes "recording"
    bridge.state_changed.emit("recording")
    QApplication.processEvents()

    # Previous session steps must be cleared
    assert len(panel._steps) == 0
    assert panel.step_list.count() == 0

    # New session starts at #1
    new_step1 = Step(
        id="s_new_1", seq=1, action=ActionType.CLICK, created_at="2026-10-08T00:01:00Z", monotonic_ms=300,
        process=ProcessFacts(pid=200, exe_name="chrome.exe"),
        window=WindowFacts(handle=2, title="Google Chrome", class_name="Chrome_WidgetWin_1")
    )
    bridge.step_added.emit(new_step1)
    QApplication.processEvents()

    assert len(panel._steps) == 1
    assert panel._steps[0].id == "s_new_1"
    assert panel._steps[0].seq == 1
    assert panel.step_list.count() == 1
    assert "1 step" in panel.lbl_title.text()

    # Test Clear button updates header to 0 steps and empties list
    from unittest.mock import patch
    from PyQt6.QtWidgets import QMessageBox
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        panel._on_clear_clicked()
    assert len(panel._steps) == 0
    assert panel.step_list.count() == 0
    assert "0 steps" in panel.lbl_title.text()

    dlg.close()
    bridge.dispose()


def test_timeline_switch_window_step_display(qapp, fake_service):
    svc, bus = fake_service
    bridge = RecorderQtBridge(svc)
    panel = RecorderPanel(svc, bridge)

    switch_step = Step(
        id="sw_1", seq=1, action=ActionType.SWITCH_WINDOW,
        created_at="2026-10-08T00:00:00Z", monotonic_ms=100,
        process=ProcessFacts(pid=100, exe_name="explorer.exe"),
        window=WindowFacts(handle=50, title="Downloads", class_name="CabinetWClass"),
        params={"title": "Downloads"}
    )
    bridge.step_added.emit(switch_step)
    QApplication.processEvents()

    panel.step_list.setCurrentRow(0)
    QApplication.processEvents()

    # Should clearly explain window switch instead of "No locators synthesized" / "UNRESOLVED"
    assert "Window Switch" in panel.lbl_locator_state.text()
    assert "Target Window: Downloads" in panel.combo_locators.currentText()

    panel.close()
    bridge.dispose()


def test_lean_finalized_outputs_exactly_two_files(tmp_path):
    """Verify that finalized recording folder produces strictly 2 files: actions.json and recording.json with lean size."""
    import json
    from pathlib import Path
    from xgen.recorder.adapters.jsonl_store import JsonlRecordingStore
    from xgen.recorder.models import (
        ActionType, ElementChain, ElementFacts, LocatorCandidate, LocatorState,
        ProcessFacts, Recording, RecordingMeta, Step, WindowFacts
    )

    test_dir = tmp_path / "test_store_two_files"
    test_dir.mkdir(parents=True, exist_ok=True)
    store = JsonlRecordingStore(root_dir=test_dir)

    meta = RecordingMeta(id="rec-two-files", name="TwoFilesDemo", started_at="2026-10-08T00:00:00Z")
    store.create(meta)

    session_dir = test_dir / "rec-two-files"
    assert (session_dir / "meta.json").exists()
    assert (session_dir / "journal.jsonl").exists()

    # Append 10 steps with deep ancestors
    steps = []
    for i in range(1, 11):
        step = Step(
            id=f"step-{i}", seq=i, action=ActionType.CLICK, created_at="2026-10-08T00:00:01Z", monotonic_ms=i * 100,
            process=ProcessFacts(pid=1234, exe_name="app.exe"),
            window=WindowFacts(handle=10, title="Main App", class_name="AppWnd"),
            target=ElementChain(
                target=ElementFacts(control_type="Button", name=f"Btn{i}"),
                ancestors=tuple([ElementFacts(control_type="Pane") for _ in range(20)]),
                window=WindowFacts(handle=10, title="Main App", class_name="AppWnd"),
                process=ProcessFacts(pid=1234, exe_name="app.exe")
            ),
            locators=[
                LocatorCandidate(xpath=f"//Button[@Name='Btn{i}']", tier="1", stability_score=90, state=LocatorState.UNIQUE_IN_EVIDENCE)
            ]
        )
        steps.append(step)
        store.append_step("rec-two-files", step)

    rec = Recording(meta=meta, steps=steps)
    store.finalize(rec)

    # Must contain strictly 2 files
    files = sorted([f.name for f in session_dir.iterdir() if f.is_file()])
    assert files == ["actions.json", "recording.json"], f"Expected exactly 2 files, found: {files}"

    # Verify actions.json format
    with open(session_dir / "actions.json", "r", encoding="utf-8") as f:
        actions_data = json.load(f)
    assert len(actions_data) == 10
    assert actions_data["1"] == ["click", "//Button[@Name='Btn1']"]
    assert actions_data["10"] == ["click", "//Button[@Name='Btn10']"]

    # Verify recording.json format and size
    with open(session_dir / "recording.json", "r", encoding="utf-8") as f:
        rec_data = json.load(f)
    assert rec_data["meta"]["id"] == "rec-two-files"
    assert len(rec_data["steps"]) == 10
    assert rec_data["steps"][0]["target"]["target"]["name"] == "Btn1"

    # Size check: 10 steps should be under 15 KB (previously ~300 KB)
    rec_size = (session_dir / "recording.json").stat().st_size
    assert rec_size < 15000, f"recording.json is too large ({rec_size} bytes), expected < 15000 bytes"


def test_step_deletion_and_resequencing_in_ui(qapp, fake_service):
    """Verify that deleting a step from UI re-sequences remaining steps and updates badges cleanly."""
    svc, bus = fake_service
    bridge = RecorderQtBridge(svc)
    panel = RecorderPanel(svc, bridge)

    proc = ProcessFacts(pid=100, exe_name="app.exe")
    win = WindowFacts(handle=10, title="Main", class_name="AppWnd")

    steps = [
        Step(id="s1", seq=1, action=ActionType.CLICK, created_at="2026-10-08T00:00:01Z", monotonic_ms=100, process=proc, window=win),
        Step(id="s2", seq=2, action=ActionType.TYPE, created_at="2026-10-08T00:00:02Z", monotonic_ms=200, process=proc, window=win, params={"text": "hello"}),
        Step(id="s3", seq=3, action=ActionType.KEY_PRESS, created_at="2026-10-08T00:00:03Z", monotonic_ms=300, process=proc, window=win, params={"keys": ["Enter"]}),
    ]

    for s in steps:
        bridge.step_added.emit(s)
    QApplication.processEvents()

    assert len(panel._steps) == 3
    assert panel.step_list.count() == 3

    # Select step 2
    panel.step_list.setCurrentRow(1)
    QApplication.processEvents()
    assert panel._current_step_id == "s2"
    assert panel.btn_delete_step.isEnabled() is True

    # Delete step 2 via button click
    panel.btn_delete_step.click()
    QApplication.processEvents()

    # Steps list in UI should now have 2 items, re-sequenced to 1 and 2
    assert len(panel._steps) == 2
    assert panel.step_list.count() == 2
    assert panel._steps[0].id == "s1"
    assert panel._steps[0].seq == 1
    assert panel._steps[1].id == "s3"
    assert panel._steps[1].seq == 2
    assert "2 steps" in panel.lbl_title.text()

    # Test keyboard deletion on step 1
    panel.step_list.setCurrentRow(0)
    QApplication.processEvents()
    assert panel._current_step_id == "s1"

    key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    panel.keyPressEvent(key_event)
    QApplication.processEvents()

    assert len(panel._steps) == 1
    assert panel._steps[0].id == "s3"
    assert panel._steps[0].seq == 1
    assert "1 step" in panel.lbl_title.text()

    panel.close()
    bridge.dispose()


def test_completed_recording_step_deletion_persists(tmp_path):
    """Verify that deleting a step on a completed recording updates disk files (actions.json and recording.json)."""
    import json
    from pathlib import Path
    from xgen.recorder.adapters.jsonl_store import JsonlRecordingStore
    from xgen.recorder.service import RecorderService
    from tests.recorder.fakes import FakeClock, FakeInputSource, FakeContextProvider
    from xgen.recorder.models import ActionType, ProcessFacts, Recording, RecordingMeta, Step, WindowFacts

    test_dir = tmp_path / "test_delete_persistence"
    test_dir.mkdir(parents=True, exist_ok=True)
    store = JsonlRecordingStore(root_dir=test_dir)

    meta = RecordingMeta(id="rec-del-test", name="DeleteTest", started_at="2026-10-08T00:00:00Z", stopped_at="2026-10-08T00:01:00Z")
    store.create(meta)

    proc = ProcessFacts(pid=100, exe_name="app.exe")
    win = WindowFacts(handle=10, title="Main", class_name="AppWnd")

    steps = [
        Step(id="st-1", seq=1, action=ActionType.CLICK, created_at="2026-10-08T00:00:01Z", monotonic_ms=100, process=proc, window=win),
        Step(id="st-2", seq=2, action=ActionType.CLICK, created_at="2026-10-08T00:00:02Z", monotonic_ms=200, process=proc, window=win),
        Step(id="st-3", seq=3, action=ActionType.CLICK, created_at="2026-10-08T00:00:03Z", monotonic_ms=300, process=proc, window=win),
    ]
    rec = Recording(meta=meta, steps=steps)
    store.finalize(rec)

    svc = RecorderService(
        clock=FakeClock(),
        input_source=FakeInputSource(),
        context_provider=FakeContextProvider(),
        store=store
    )

    # Delete the middle step
    ok = svc.delete_step("st-2")
    assert ok is True

    # Check persisted files on disk
    session_dir = test_dir / "rec-del-test"
    with open(session_dir / "actions.json", "r", encoding="utf-8") as f:
        actions_data = json.load(f)
    assert len(actions_data) == 2
    assert "1" in actions_data and "2" in actions_data
    assert "3" not in actions_data

    with open(session_dir / "recording.json", "r", encoding="utf-8") as f:
        rec_data = json.load(f)
    assert len(rec_data["steps"]) == 2
    assert rec_data["steps"][0]["id"] == "st-1"
    assert rec_data["steps"][0]["seq"] == 1
    assert rec_data["steps"][1]["id"] == "st-3"
    assert rec_data["steps"][1]["seq"] == 2


def test_locator_combobox_popup_constraints_and_tooltips(qapp, fake_service):
    """Verify LocatorComboBox constraints, item data tooltips, and elision."""
    from xgen.ui.recorder.panel import LocatorComboBox
    svc, bus = fake_service
    bridge = RecorderQtBridge(svc)
    dlg = RecorderTimelineDialog(svc, bridge)
    panel = dlg.panel

    assert isinstance(panel.combo_locators, LocatorComboBox)
    assert panel.combo_locators.maxVisibleItems() == 8

    step = Step(
        id="s1", seq=1, action=ActionType.CLICK, created_at="2026-10-08T00:00:00Z", monotonic_ms=100,
        process=ProcessFacts(pid=100, exe_name="app.exe"),
        window=WindowFacts(handle=1, title="Test Window", class_name="TestClass"),
        locators=[
            LocatorCandidate(xpath="//Group[contains(@ClassName, 'relative')]//ComboBox[@Name='Message input']", tier="TIER_1", stability_score=90, state=LocatorState.UNIQUE_IN_EVIDENCE),
            LocatorCandidate(xpath="//*[@AutomationId='antigravity.agentSidePanelInputBox']", tier="TIER_2", stability_score=80, state=LocatorState.UNVERIFIED),
        ]
    )
    bridge.step_added.emit(step)
    QApplication.processEvents()

    panel.step_list.setCurrentRow(0)
    QApplication.processEvents()

    # ComboBox populated with items and tooltips
    assert panel.combo_locators.count() == 2
    tip = panel.combo_locators.itemData(0, Qt.ItemDataRole.ToolTipRole)
    assert "//Group[contains" in tip
    assert "Active XPath:" in panel.combo_locators.toolTip()


def test_timeline_delete_step_undo_cache_and_restoration(qapp, fake_service):
    """Test that deleting a step caches it, enables Undo, and restores it on click."""
    svc, bus = fake_service
    bridge = RecorderQtBridge(svc)
    dlg = RecorderTimelineDialog(svc, bridge)
    panel = dlg.panel

    proc = ProcessFacts(pid=100, exe_name="app.exe")
    win = WindowFacts(handle=1, title="Test", class_name="Wnd")

    step1 = Step(id="s1", seq=1, action=ActionType.CLICK, created_at="2026-10-08T00:00:00Z", monotonic_ms=100, process=proc, window=win)
    step2 = Step(id="s2", seq=2, action=ActionType.TYPE, created_at="2026-10-08T00:00:01Z", monotonic_ms=200, process=proc, window=win, params={"text": "hello"})
    step3 = Step(id="s3", seq=3, action=ActionType.KEY_PRESS, created_at="2026-10-08T00:00:02Z", monotonic_ms=300, process=proc, window=win)

    meta1 = RecordingMeta(id="rec-del-undo", name="TestDelUndo", started_at="2026-10-08T00:00:00Z")
    svc._active_recording = Recording(meta=meta1, steps=[step1, step2, step3])

    bridge.step_added.emit(step1)
    bridge.step_added.emit(step2)
    bridge.step_added.emit(step3)
    QApplication.processEvents()

    assert len(panel._steps) == 3
    assert panel.btn_undo.isEnabled() is False

    # Select step 2 and delete it
    panel.step_list.setCurrentRow(1)
    panel.btn_delete_step.click()
    QApplication.processEvents()

    assert len(panel._steps) == 2
    assert [s.id for s in panel._steps] == ["s1", "s3"]
    # Undo should now be enabled with cached step
    assert panel.btn_undo.isEnabled() is True
    assert len(panel._deleted_steps_cache) == 1
    assert panel._deleted_steps_cache[0][0].id == "s2"

    # Click Undo to restore
    panel.btn_undo.click()
    QApplication.processEvents()

    assert len(panel._steps) == 3
    assert [s.id for s in panel._steps] == ["s1", "s2", "s3"]
    assert panel._steps[1].params.get("text") == "hello"
    assert panel.btn_undo.isEnabled() is False


def test_timeline_save_step_notes_and_locator_changes(qapp, fake_service):
    """Test editing step notes and locators, then saving via the Save button."""
    svc, bus = fake_service
    bridge = RecorderQtBridge(svc)
    dlg = RecorderTimelineDialog(svc, bridge)
    panel = dlg.panel

    proc = ProcessFacts(pid=100, exe_name="app.exe")
    win = WindowFacts(handle=1, title="Test", class_name="Wnd")

    step = Step(
        id="s1", seq=1, action=ActionType.CLICK, created_at="2026-10-08T00:00:00Z", monotonic_ms=100,
        process=proc, window=win,
        locators=[
            LocatorCandidate(xpath="//Button[@Name='OK']", tier="TIER_1", stability_score=95, state=LocatorState.UNIQUE_IN_EVIDENCE),
            LocatorCandidate(xpath="//*[@AutomationId='btnOK']", tier="TIER_2", stability_score=85, state=LocatorState.UNVERIFIED),
        ]
    )
    meta2 = RecordingMeta(id="rec-save-test", name="SaveTest", started_at="2026-10-08T00:00:00Z")
    svc._active_recording = Recording(meta=meta2, steps=[step])

    bridge.step_added.emit(step)
    QApplication.processEvents()

    panel.step_list.setCurrentRow(0)
    assert panel.btn_save.isEnabled() is True

    # Edit notes and change locator dropdown
    panel.txt_notes.setText("Validated login confirmation button")
    panel.combo_locators.setCurrentIndex(1)

    panel.btn_save.click()
    QApplication.processEvents()

    # Step in panel and in service has updated notes and selected locator
    updated = panel._steps[0]
    assert updated.notes == "Validated login confirmation button"
    assert updated.selected_locator == 1
    assert svc.get_step("s1").notes == "Validated login confirmation button"


def test_timeline_ctrl_z_undo_and_ctrl_s_save_shortcuts(qapp, fake_service):
    """Test that Ctrl+Z undoes step deletion and Ctrl+S saves edits."""
    svc, bus = fake_service
    bridge = RecorderQtBridge(svc)
    dlg = RecorderTimelineDialog(svc, bridge)
    panel = dlg.panel

    proc = ProcessFacts(pid=100, exe_name="app.exe")
    win = WindowFacts(handle=1, title="Test", class_name="Wnd")
    step1 = Step(id="s1", seq=1, action=ActionType.CLICK, created_at="2026-10-08T00:00:00Z", monotonic_ms=100, process=proc, window=win)
    step2 = Step(id="s2", seq=2, action=ActionType.TYPE, created_at="2026-10-08T00:00:01Z", monotonic_ms=200, process=proc, window=win)

    meta = RecordingMeta(id="rec-shortcut", name="Shortcuts", started_at="2026-10-08T00:00:00Z")
    svc._active_recording = Recording(meta=meta, steps=[step1, step2])
    bridge.step_added.emit(step1)
    bridge.step_added.emit(step2)
    QApplication.processEvents()

    # Delete step 2 using Del key
    panel.step_list.setCurrentRow(1)
    del_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    panel.keyPressEvent(del_event)
    QApplication.processEvents()
    assert len(panel._steps) == 1

    # Undo using Ctrl+Z
    ctrl_z = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    panel.keyPressEvent(ctrl_z)
    QApplication.processEvents()
    assert len(panel._steps) == 2
    assert panel._steps[1].id == "s2"

    # Edit notes and save using Ctrl+S
    panel.step_list.setCurrentRow(0)
    panel.txt_notes.setText("Saved with Ctrl+S")
    ctrl_s = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    panel.keyPressEvent(ctrl_s)
    QApplication.processEvents()
    assert panel._steps[0].notes == "Saved with Ctrl+S"




