"""
Hardening and Resilience Tests (Phase 8).
Validates redaction rules, secret-field suppression, never_store_text,
target scoping & PID self-exclusion, backpressure drop policy, failure mode resilience,
recovery from incomplete journals, and rapid interaction soak simulation.
"""
import dataclasses
import queue
import time
from typing import List, Optional
import pytest

from xgen.recorder.adapters.jsonl_store import JsonlRecordingStore
from xgen.recorder.adapters.passive_input import PassiveInputSource
from xgen.recorder.capture.interpreter import ActionInterpreter
from xgen.recorder.events import ErrorEvent, EventBus, StepRecordedEvent
from xgen.recorder.models import (
    ActionType, Bounds, CapturedContext, ElementChain, ElementFacts,
    ProcessFacts, RawInputEvent, RecordingMeta, ResolutionMethod, Step, WindowFacts
)
from xgen.recorder.options import (
    CaptureOptions, RecordingOptions, RedactionRule, TargetScopeOptions
)
from xgen.recorder.ports.clock import Clock
from xgen.recorder.ports.context import NativeContextProvider
from xgen.recorder.ports.input_source import InputSource
from xgen.recorder.service import RecorderService


class FakeClock(Clock):
    def __init__(self):
        self._mono_ms = 1000
        self._wall_time = "2026-10-08T00:00:00Z"

    def monotonic_ms(self) -> int:
        return self._mono_ms

    def wall_time_iso(self) -> str:
        return self._wall_time

    def advance(self, ms: int) -> None:
        self._mono_ms += ms


class FakeInputSource(InputSource):
    def __init__(self):
        self._sink = None
        self._running = False

    def start(self, sink) -> None:
        self._sink = sink
        self._running = True

    def stop(self) -> None:
        self._running = False
        self._sink = None

    def is_running(self) -> bool:
        return self._running

    def emit(self, event: RawInputEvent) -> None:
        if self._sink:
            self._sink(event)


class FakeContextProvider(NativeContextProvider):
    def __init__(self, default_ctx: Optional[CapturedContext] = None):
        self.default_ctx = default_ctx

    def cursor_position(self):
        return (100, 100)

    def capture_at(self, x: int, y: int, *, deadline_ms: int = 150):
        return self.default_ctx

    def capture_focused(self, *, deadline_ms: int = 150):
        return self.default_ctx

    def find_similar(self, ctx, *, limit: int = 10, deadline_ms: int = 80):
        from xgen.recorder.models import SimilarFacts
        return SimilarFacts(count=1, handles=(1001,))


def make_context(pid: int = 4242, proc_name: str = "notepad.exe",
                 win_title: str = "Untitled - Notepad",
                 target_name: str = "Text Editor",
                 is_password: bool = False) -> CapturedContext:
    target = ElementFacts(
        control_type="Edit",
        name=target_name,
        automation_id="txtEdit",
        is_password=is_password,
        bounds=Bounds(10, 10, 100, 100)
    )
    chain = ElementChain(
        target=target,
        ancestors=[],
        window=WindowFacts(handle=1001, title=win_title, class_name="Notepad"),
        process=ProcessFacts(pid=pid, exe_name=proc_name),
        complete=True
    )
    return CapturedContext(
        chain=chain,
        resolution=ResolutionMethod.NATIVE_EXACT,
        captured_at_ms=1000,
        snapshot_cost_ms=5
    )


def test_redaction_rule_text_masking():
    """Verify regex rule masks sensitive typed text before Step creation."""
    rule = RedactionRule(pattern=r"secret_\d+", replacement="[TOKEN]")
    options = CaptureOptions(redaction_rules=[rule])
    interp = ActionInterpreter(options=options)

    # Type 'secret_12345'
    ctx = make_context()
    for ch in "secret_12345":
        interp.feed_input(RawInputEvent("key_down", key_name=ch, monotonic_ms=100), ctx=ctx)

    steps = interp.flush(now_ms=200)
    assert len(steps) == 1
    assert steps[0].action == ActionType.TYPE
    assert steps[0].params["text"] == "[TOKEN]"


def test_redaction_rule_text_dropping():
    """Verify regex rule with action='drop' completely drops sensitive typed step."""
    rule = RedactionRule(pattern=r"DROP_ME", action="drop")
    options = CaptureOptions(redaction_rules=[rule])
    interp = ActionInterpreter(options=options)

    ctx = make_context()
    for ch in "DROP_ME_NOW":
        interp.feed_input(RawInputEvent("key_down", key_name=ch, monotonic_ms=100), ctx=ctx)

    steps = interp.flush(now_ms=200)
    assert len(steps) == 0


def test_redaction_rule_name_masking_and_dropping():
    """Verify rules scoped to 'name' mask or drop elements with sensitive names."""
    mask_rule = RedactionRule(pattern=r"Confidential", replacement="[REDACTED_NAME]", scope="name")
    drop_rule = RedactionRule(pattern=r"TopSecret", action="drop", scope="name")
    options = CaptureOptions(redaction_rules=[mask_rule, drop_rule])
    interp = ActionInterpreter(options=options)

    # 1. Masked element
    ctx_masked = make_context(target_name="Confidential Project")
    steps1 = interp.feed_input(RawInputEvent("mouse_down", x=50, y=50, monotonic_ms=100), ctx=ctx_masked)
    steps1 += interp.feed_input(RawInputEvent("mouse_up", x=50, y=50, monotonic_ms=110), ctx=ctx_masked)
    assert len(steps1) == 1
    assert steps1[0].target.target.name == "[REDACTED_NAME] Project"

    # 2. Dropped element
    ctx_dropped = make_context(target_name="TopSecret Project")
    steps2 = interp.feed_input(RawInputEvent("mouse_down", x=50, y=50, monotonic_ms=200), ctx=ctx_dropped)
    steps2 += interp.feed_input(RawInputEvent("mouse_up", x=50, y=50, monotonic_ms=210), ctx=ctx_dropped)
    assert len(steps2) == 0


def test_never_store_text_mode():
    """Verify never_store_text suppresses all typed characters and marks secret."""
    options = CaptureOptions(never_store_text=True)
    interp = ActionInterpreter(options=options)

    ctx = make_context()
    for ch in "hello_world":
        interp.feed_input(RawInputEvent("key_down", key_name=ch, monotonic_ms=100), ctx=ctx)

    steps = interp.flush(now_ms=200)
    assert len(steps) == 1
    assert steps[0].action == ActionType.TYPE
    assert steps[0].params["text"] == ""
    assert steps[0].params["secret"] is True


def test_password_field_suppression():
    """Verify password fields automatically mask text when mask_password_fields is True."""
    options = CaptureOptions(mask_password_fields=True)
    interp = ActionInterpreter(options=options)

    pw_ctx = make_context(is_password=True)
    for ch in "MySecret123":
        interp.feed_input(RawInputEvent("key_down", key_name=ch, monotonic_ms=100), ctx=pw_ctx)

    steps = interp.flush(now_ms=200)
    assert len(steps) == 1
    assert steps[0].params["text"] == ""
    assert steps[0].params["secret"] is True


def test_target_scope_pid_exclusion(tmp_path):
    """Verify excluded PIDs (such as xGen's own PID) are completely ignored by RecorderService."""
    clock = FakeClock()
    inp = FakeInputSource()
    ctx = make_context(pid=9999, proc_name="xgen.exe")
    prov = FakeContextProvider(default_ctx=ctx)
    store = JsonlRecordingStore(root_dir=tmp_path)
    service = RecorderService(clock=clock, input_source=inp, context_provider=prov, store=store)

    opts = RecordingOptions(
        target_scope=TargetScopeOptions(exclude_pids=[9999])
    )
    service.start(opts)

    inp.emit(RawInputEvent("mouse_down", x=50, y=50, monotonic_ms=100))
    inp.emit(RawInputEvent("mouse_up", x=50, y=50, monotonic_ms=120))

    meta = service.stop()
    assert meta.step_count == 0
    assert len(service.get_steps().steps) == 0


def test_target_scope_process_name_and_title_filtering(tmp_path):
    """Verify process name and window title regex filters."""
    clock = FakeClock()
    inp = FakeInputSource()
    ctx_calculator = make_context(pid=100, proc_name="CalculatorApp.exe", win_title="Calculator")
    ctx_notepad = make_context(pid=200, proc_name="Notepad.exe", win_title="Untitled - Notepad")
    prov = FakeContextProvider(default_ctx=ctx_calculator)
    store = JsonlRecordingStore(root_dir=tmp_path)
    service = RecorderService(clock=clock, input_source=inp, context_provider=prov, store=store)

    # Only include Notepad
    opts = RecordingOptions(
        target_scope=TargetScopeOptions(
            include_process_names=["notepad"],
            include_window_titles_regex=[r".*Notepad.*"]
        )
    )
    service.start(opts)

    # 1. Emit click on Calculator (should be ignored)
    inp.emit(RawInputEvent("mouse_down", x=10, y=10, monotonic_ms=100))
    inp.emit(RawInputEvent("mouse_up", x=10, y=10, monotonic_ms=120))
    assert len(service.get_steps().steps) == 0

    # 2. Switch context to Notepad (should be captured)
    prov.default_ctx = ctx_notepad
    inp.emit(RawInputEvent("mouse_down", x=20, y=20, monotonic_ms=200))
    inp.emit(RawInputEvent("mouse_up", x=20, y=20, monotonic_ms=220))

    meta = service.stop()
    assert meta.step_count == 1
    assert service.get_steps().steps[0].window.title == "Untitled - Notepad"


def test_backpressure_queue_overflow():
    """Verify PassiveInputSource drops events when queue fills without blocking the caller."""
    source = PassiveInputSource(max_queue_size=5)

    sink_events = []
    # Start without consuming immediately (or slowly)
    source.start(sink=lambda e: sink_events.append(e))

    # Flood queue directly via callbacks
    class DummyButton:
        name = "left"

    # Push 50 events rapidly
    for i in range(50):
        source._on_mouse_click(i, i, DummyButton(), True)

    assert source.dropped_count > 0
    source.stop()


def test_failure_mode_locator_synthesis_crash(tmp_path):
    """Verify that if locator synthesis throws an exception, step is flagged and recorded safely."""
    clock = FakeClock()
    inp = FakeInputSource()
    ctx = make_context()
    prov = FakeContextProvider(default_ctx=ctx)
    store = JsonlRecordingStore(root_dir=tmp_path)

    # Mock locator engine to raise an exception
    class FailingLocatorEngine:
        def generate_locators(self, ctx, similar):
            raise RuntimeError("COM ElementNotAvailableException simulation")

    service = RecorderService(
        clock=clock, input_source=inp, context_provider=prov, store=store,
        locator_engine=FailingLocatorEngine()
    )
    service.start()

    inp.emit(RawInputEvent("mouse_down", x=10, y=10, monotonic_ms=100))
    inp.emit(RawInputEvent("mouse_up", x=10, y=10, monotonic_ms=120))

    steps = service.get_steps().steps
    assert len(steps) == 1
    assert any("synthesis_error" in f for f in steps[0].flags)
    service.stop()


def test_failure_mode_store_write_error(tmp_path):
    """Verify that store append errors publish an ErrorEvent without crashing the session."""
    clock = FakeClock()
    inp = FakeInputSource()
    ctx = make_context()
    prov = FakeContextProvider(default_ctx=ctx)

    class FailingStore(JsonlRecordingStore):
        def append_step(self, recording_id: str, step: Step) -> None:
            raise OSError("Disk full simulation")

    store = FailingStore(root_dir=tmp_path)
    bus = EventBus()
    errors: List[ErrorEvent] = []
    bus.subscribe(ErrorEvent, lambda e: errors.append(e))

    service = RecorderService(
        clock=clock, input_source=inp, context_provider=prov, store=store,
        event_bus=bus
    )
    service.start()

    inp.emit(RawInputEvent("mouse_down", x=10, y=10, monotonic_ms=100))
    inp.emit(RawInputEvent("mouse_up", x=10, y=10, monotonic_ms=120))

    assert len(errors) == 1
    assert errors[0].code == "store_write_error"
    assert len(service.get_steps().steps) == 1


def test_incomplete_recording_recovery(tmp_path):
    """Verify that an unfinalized session killed before stop() can be reconstructed from journal.jsonl."""
    store = JsonlRecordingStore(root_dir=tmp_path)
    meta = RecordingMeta(id="crash-sess-1", name="Crashed Session", started_at="2026-10-08T00:00:00Z")
    store.create(meta)

    # Append 3 steps to the journal
    ctx = make_context()
    for i in range(1, 4):
        s = Step(
            id=f"step-{i}",
            seq=i,
            action=ActionType.CLICK,
            created_at="2026-10-08T00:00:01Z",
            monotonic_ms=1000 + i * 100,
            process=ctx.chain.process,
            window=ctx.chain.window,
            target=ctx.chain,
            params={"x": i * 10, "y": i * 10, "button": "left"},
            resolution=ResolutionMethod.NATIVE_EXACT
        )
        store.append_step(meta.id, s)

    # Notice: finalize() is intentionally NOT called!
    incomplete = store.incomplete()
    assert len(incomplete) == 1
    assert incomplete[0].id == "crash-sess-1"

    # Load and reconstruct
    rec = store.load("crash-sess-1")
    assert rec.meta.id == "crash-sess-1"
    assert len(rec.steps) == 3
    assert [s.seq for s in rec.steps] == [1, 2, 3]


def test_soak_rapid_interaction_simulation(tmp_path):
    """Soak simulation: flood 300 rapid interleaved actions, verify consistency and no leaks."""
    clock = FakeClock()
    inp = FakeInputSource()
    ctx = make_context()
    prov = FakeContextProvider(default_ctx=ctx)
    store = JsonlRecordingStore(root_dir=tmp_path)
    service = RecorderService(clock=clock, input_source=inp, context_provider=prov, store=store)

    service.start()
    t = 1000

    for i in range(100):
        # Click
        inp.emit(RawInputEvent("mouse_down", x=i, y=i, monotonic_ms=t))
        t += 10
        inp.emit(RawInputEvent("mouse_up", x=i, y=i, monotonic_ms=t))
        t += 20

        # Typing
        inp.emit(RawInputEvent("key_down", key_name="a", monotonic_ms=t))
        t += 10
        inp.emit(RawInputEvent("key_down", key_name="b", monotonic_ms=t))
        t += 500  # Exceeds typing debounce -> flushes typing
        clock.advance(540)

    meta = service.stop()
    assert meta.step_count > 100
    steps = service.get_steps().steps
    # Verify sequential ordering is strictly monotonic
    for idx, s in enumerate(steps):
        assert s.seq == idx + 1
