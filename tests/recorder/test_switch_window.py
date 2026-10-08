"""
Unit test for derived SWITCH_WINDOW insertion (Phase 5.6).
Verifies that when user transitions between different top-level windows,
a SWITCH_WINDOW step is cleanly inserted before the subsequent interaction.
"""
from xgen.recorder.adapters.jsonl_store import JsonlRecordingStore
from xgen.recorder.models import (
    ActionType, Bounds, CapturedContext, ElementChain, ElementFacts,
    ProcessFacts, RawInputEvent, ResolutionMethod, WindowFacts
)
from xgen.recorder.ports.clock import Clock
from xgen.recorder.ports.context import NativeContextProvider
from xgen.recorder.ports.input_source import InputSource
from xgen.recorder.service import RecorderService


class FakeClock(Clock):
    def monotonic_ms(self) -> int: return 1000
    def wall_time_iso(self) -> str: return "2026-10-08T00:00:00Z"


class FakeInputSource(InputSource):
    def __init__(self):
        self._sink = None
    def start(self, sink) -> None: self._sink = sink
    def stop(self) -> None: self._sink = None
    def is_running(self) -> bool: return self._sink is not None
    def emit(self, event) -> None:
        if self._sink: self._sink(event)


class FakeContextProvider(NativeContextProvider):
    def __init__(self, ctx):
        self.ctx = ctx
    def cursor_position(self): return (100, 100)
    def capture_at(self, x, y, *, deadline_ms=150): return self.ctx
    def capture_focused(self, *, deadline_ms=150): return self.ctx
    def find_similar(self, ctx, *, limit=10, deadline_ms=80):
        from xgen.recorder.models import SimilarFacts
        return SimilarFacts(count=1, handles=(1001,))


def make_context(hwnd: int, title: str) -> CapturedContext:
    target = ElementFacts(control_type="Button", name="Btn", bounds=Bounds(10, 10, 50, 50))
    chain = ElementChain(
        target=target,
        ancestors=[],
        window=WindowFacts(handle=hwnd, title=title, class_name="TestClass"),
        process=ProcessFacts(pid=123, exe_name="test.exe"),
        complete=True
    )
    return CapturedContext(
        chain=chain,
        resolution=ResolutionMethod.NATIVE_EXACT,
        captured_at_ms=1000,
        snapshot_cost_ms=2
    )


def test_derived_switch_window_insertion(tmp_path):
    clock = FakeClock()
    inputs = FakeInputSource()
    ctx_w1 = make_context(0x1000, "Window 1")
    provider = FakeContextProvider(ctx_w1)
    store = JsonlRecordingStore(root_dir=tmp_path)
    service = RecorderService(clock=clock, input_source=inputs, context_provider=provider, store=store)

    service.start()

    # 1. Action in Window 1
    inputs.emit(RawInputEvent("mouse_down", x=20, y=20, monotonic_ms=100))
    inputs.emit(RawInputEvent("mouse_up", x=20, y=20, monotonic_ms=120))

    # 2. Action in Window 2
    provider.ctx = make_context(0x2000, "Dialog Window 2")
    inputs.emit(RawInputEvent("mouse_down", x=30, y=30, monotonic_ms=200))
    inputs.emit(RawInputEvent("mouse_up", x=30, y=30, monotonic_ms=220))

    meta = service.stop()
    steps = service.get_steps().steps

    # Step count should be 3: Click(W1), SwitchWindow(W2), Click(W2)
    assert meta.step_count == 3
    assert len(steps) == 3

    assert steps[0].action == ActionType.CLICK
    assert steps[0].seq == 1
    assert steps[0].window.handle == 0x1000

    assert steps[1].action == ActionType.SWITCH_WINDOW
    assert steps[1].seq == 2
    assert steps[1].window.handle == 0x2000
    assert steps[1].params["title"] == "Dialog Window 2"
    assert steps[1].to_action_array() == ["switch_window", "", "Dialog Window 2"]

    assert steps[2].action == ActionType.CLICK
    assert steps[2].seq == 3
    assert steps[2].window.handle == 0x2000


def test_popup_and_menu_do_not_trigger_switch_window(tmp_path):
    clock = FakeClock()
    inputs = FakeInputSource()
    ctx_w1 = make_context(0x1000, "Window 1")
    provider = FakeContextProvider(ctx_w1)
    store = JsonlRecordingStore(root_dir=tmp_path)
    service = RecorderService(clock=clock, input_source=inputs, context_provider=provider, store=store)

    service.start()

    # 1. Action in Window 1 (main window)
    inputs.emit(RawInputEvent("mouse_down", x=20, y=20, monotonic_ms=100))
    inputs.emit(RawInputEvent("mouse_up", x=20, y=20, monotonic_ms=120))

    # 2. Action in Context Menu (kind="menu")
    target = ElementFacts(control_type="MenuItem", name="Refresh", bounds=Bounds(10, 10, 50, 50))
    chain = ElementChain(
        target=target,
        ancestors=[],
        window=WindowFacts(handle=0x5000, title="Desktop Context Menu", class_name="#32768", kind="menu"),
        process=ProcessFacts(pid=123, exe_name="explorer.exe"),
        complete=True
    )
    provider.ctx = CapturedContext(chain=chain, resolution=ResolutionMethod.NATIVE_EXACT, captured_at_ms=1000, snapshot_cost_ms=2)

    inputs.emit(RawInputEvent("mouse_down", x=30, y=30, monotonic_ms=200))
    inputs.emit(RawInputEvent("mouse_up", x=30, y=30, monotonic_ms=220))

    meta = service.stop()
    steps = service.get_steps().steps

    # Step count should be 2: Click(W1), Click(Menu) - NO switch_window step!
    assert meta.step_count == 2
    assert len(steps) == 2
    assert steps[0].action == ActionType.CLICK
    assert steps[1].action == ActionType.CLICK
    assert steps[1].window.kind == "menu"
    assert steps[1].window.title == "Desktop Context Menu"

