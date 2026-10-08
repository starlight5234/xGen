"""
Tests for RecorderService lifecycle, state management, and API operations.
Uses test fakes to verify complete recording flow in memory.
"""
import pytest
from tests.recorder.fakes import (
    FakeClock, FakeContextProvider, FakeExporter, FakeInputSource,
    InMemoryRecordingStore
)
from xgen.recorder.api import RecorderError, RecorderErrorCode
from xgen.recorder.events import (
    EventBus, StateChangedEvent, StepDeletedEvent, StepRecordedEvent,
    StepUpdatedEvent
)
from xgen.recorder.models import (
    ActionType, LocatorCandidate, RawInputEvent, RecorderState
)
from xgen.recorder.options import RecordingOptions
from xgen.recorder.service import RecorderService


@pytest.fixture
def service():
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
    return svc, clock, input_source, ctx_provider, store, bus


def test_service_lifecycle_and_events(service):
    svc, clock, input_source, ctx_provider, store, bus = service

    events_received = []
    svc.subscribe(lambda e: events_received.append(e))

    # Initial state
    assert svc.status().state == RecorderState.IDLE

    # Start recording
    rec_id = svc.start(RecordingOptions(name="TestSession"))
    assert svc.status().state == RecorderState.RECORDING
    assert svc.status().recording_id == rec_id
    assert input_source.is_running()

    # Simulate mouse click
    input_source.emit_event(RawInputEvent("mouse_down", x=150, y=200, button="left", monotonic_ms=1050))
    clock.advance_ms(50)
    input_source.emit_event(RawInputEvent("mouse_up", x=150, y=200, button="left", monotonic_ms=1100))

    # Check steps
    paged = svc.get_steps()
    assert paged.total_count == 1
    step = paged.steps[0]
    assert step.action == ActionType.CLICK
    assert len(step.locators) > 0
    assert step.selected_locator == 0
    assert step.to_action_array() == ["click", step.locators[0].xpath]

    # Pause and Resume
    svc.pause()
    assert svc.status().state == RecorderState.PAUSED

    svc.resume()
    assert svc.status().state == RecorderState.RECORDING

    # Stop recording
    meta = svc.stop()
    assert svc.status().state == RecorderState.IDLE
    assert not input_source.is_running()
    assert meta.id == rec_id
    assert meta.step_count == 1

    # Check that events fired
    state_events = [e for e in events_received if isinstance(e, StateChangedEvent)]
    assert len(state_events) >= 4  # starting, recording, paused, recording, stopping, idle
    step_events = [e for e in events_received if isinstance(e, StepRecordedEvent)]
    assert len(step_events) == 1


def test_step_editing_and_deletion(service):
    svc, clock, input_source, ctx_provider, store, bus = service

    rec_id = svc.start()
    input_source.emit_event(RawInputEvent("mouse_down", x=10, y=20, button="left", monotonic_ms=1000))
    input_source.emit_event(RawInputEvent("mouse_up", x=10, y=20, button="left", monotonic_ms=1050))

    step = svc.get_steps().steps[0]
    step_id = step.id

    # Update step notes
    updated = svc.update_step(step_id, {"notes": "My manual note"})
    assert updated.notes == "My manual note"
    assert svc.get_step(step_id).notes == "My manual note"

    # Delete step
    assert svc.delete_step(step_id) is True
    assert svc.get_steps().total_count == 0

    with pytest.raises(RecorderError) as exc_info:
        svc.get_step(step_id)
    assert exc_info.value.code == RecorderErrorCode.STEP_NOT_FOUND

    svc.stop()


def test_export_via_api(service):
    svc, clock, input_source, ctx_provider, store, bus = service

    rec_id = svc.start(RecordingOptions(name="ExportTest"))
    input_source.emit_event(RawInputEvent("mouse_down", x=10, y=20, button="left", monotonic_ms=1000))
    input_source.emit_event(RawInputEvent("mouse_up", x=10, y=20, button="left", monotonic_ms=1050))
    
    # Attach a locator to the step
    step = svc.get_steps().steps[0]
    step.locators = [LocatorCandidate(xpath="//Button[@Name='Submit']", tier="1")]
    svc.stop()

    # Export
    result = svc.export(rec_id, "action_xpath_json")
    assert result.filename == "ExportTest.json"
    assert '"click"' in result.text
    assert '"//Button[@Name=\'Submit\']"' in result.text
