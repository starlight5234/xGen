"""
Tests for ActionInterpreter.
Verifies mouse gesture resolution (click, double click, right click, drag-drop)
and keyboard typing aggregation vs special key events.
"""
import pytest
from xgen.recorder.capture.interpreter import ActionInterpreter
from xgen.recorder.models import (
    ActionType, CapturedContext, ElementChain, ElementFacts,
    ProcessFacts, RawInputEvent, ResolutionMethod, WindowFacts
)
from xgen.recorder.options import CaptureOptions


@pytest.fixture
def dummy_context():
    target = ElementFacts(control_type="Button", name="Save")
    window = WindowFacts(handle=0x100, title="Editor", class_name="QtWindow")
    proc = ProcessFacts(pid=100)
    chain = ElementChain(target=target, ancestors=(), window=window, process=proc)
    return CapturedContext(chain=chain, resolution=ResolutionMethod.NATIVE_EXACT, captured_at_ms=1000, snapshot_cost_ms=2)


def test_mouse_click_resolution(dummy_context):
    interpreter = ActionInterpreter()

    # Mouse down + up at same coordinates
    e_down = RawInputEvent(kind="mouse_down", x=100, y=100, button="left", monotonic_ms=1000)
    e_up = RawInputEvent(kind="mouse_up", x=100, y=100, button="left", monotonic_ms=1050)

    steps = interpreter.feed_input(e_down, dummy_context)
    assert len(steps) == 0

    steps = interpreter.feed_input(e_up, dummy_context)
    assert len(steps) == 1
    assert steps[0].action == ActionType.CLICK
    assert steps[0].params["button"] == "left"


def test_double_click_promotion(dummy_context):
    opts = CaptureOptions(click_debounce_ms=300)
    interpreter = ActionInterpreter(options=opts)

    # First click at t=1000
    interpreter.feed_input(RawInputEvent("mouse_down", x=100, y=100, button="left", monotonic_ms=1000), dummy_context)
    steps1 = interpreter.feed_input(RawInputEvent("mouse_up", x=100, y=100, button="left", monotonic_ms=1050), dummy_context)
    assert steps1[0].action == ActionType.CLICK

    # Second click at t=1200 (within 300ms debounce)
    interpreter.feed_input(RawInputEvent("mouse_down", x=101, y=101, button="left", monotonic_ms=1200), dummy_context)
    steps2 = interpreter.feed_input(RawInputEvent("mouse_up", x=101, y=101, button="left", monotonic_ms=1240), dummy_context)
    assert len(steps2) == 1
    assert steps2[0].action == ActionType.DOUBLE_CLICK


def test_drag_drop_detection(dummy_context):
    opts = CaptureOptions(drag_threshold_px=10)
    interpreter = ActionInterpreter(options=opts)

    # Drag from (100, 100) to (150, 100)
    e_down = RawInputEvent("mouse_down", x=100, y=100, button="left", monotonic_ms=1000)
    e_up = RawInputEvent("mouse_up", x=150, y=100, button="left", monotonic_ms=1300)

    interpreter.feed_input(e_down, dummy_context)
    steps = interpreter.feed_input(e_up, dummy_context)
    assert len(steps) == 1
    assert steps[0].action == ActionType.DRAG_DROP
    assert steps[0].params["from_x"] == 100
    assert steps[0].params["to_x"] == 150


def test_typing_aggregation_and_flush(dummy_context):
    interpreter = ActionInterpreter()

    # Feed individual characters "hello"
    chars = ["h", "e", "l", "l", "o"]
    t = 1000
    for ch in chars:
        e = RawInputEvent("key_down", key_name=ch, monotonic_ms=t)
        steps = interpreter.feed_input(e, dummy_context)
        assert len(steps) == 0  # Should aggregate, not emit immediately
        t += 50

    # Flushing emits a single 'type' step with "hello"
    flushed = interpreter.flush(now_ms=t + 100)
    assert len(flushed) == 1
    assert flushed[0].action == ActionType.TYPE
    assert flushed[0].params["text"] == "hello"
    assert flushed[0].params["secret"] is False


def test_special_key_flushes_typing(dummy_context):
    interpreter = ActionInterpreter()

    # Type "abc" then press ENTER
    interpreter.feed_input(RawInputEvent("key_down", key_name="a", monotonic_ms=1000), dummy_context)
    interpreter.feed_input(RawInputEvent("key_down", key_name="b", monotonic_ms=1050), dummy_context)
    interpreter.feed_input(RawInputEvent("key_down", key_name="c", monotonic_ms=1100), dummy_context)

    # Press ENTER
    e_enter = RawInputEvent("key_down", key_name="ENTER", monotonic_ms=1150)
    steps = interpreter.feed_input(e_enter, dummy_context)

    # Should emit 2 steps: the aggregated type step, then the key_press step
    assert len(steps) == 2
    assert steps[0].action == ActionType.TYPE
    assert steps[0].params["text"] == "abc"
    assert steps[1].action == ActionType.KEY_PRESS
    assert steps[1].params["keys"] == ["ENTER"]


def test_ctrl_a_hotkey_combination(dummy_context):
    """
    Verify that holding Left Ctrl (with OS auto-repeats) then pressing A:
    1. Emits 0 stray CTRL_L key press steps.
    2. Emits exactly 1 combined KEY_PRESS step with keys: ['CTRL', 'A'].
    3. Releasing A and Left Ctrl emits no extra steps.
    """
    interpreter = ActionInterpreter()

    # User presses and holds Left Ctrl (Windows OS auto-repeats it 3 times)
    steps1 = interpreter.feed_input(RawInputEvent("key_down", key_name="CTRL_L", monotonic_ms=1000), dummy_context)
    assert len(steps1) == 0

    steps2 = interpreter.feed_input(RawInputEvent("key_down", key_name="CTRL_L", monotonic_ms=1250), dummy_context)
    assert len(steps2) == 0

    steps3 = interpreter.feed_input(RawInputEvent("key_down", key_name="CTRL_L", monotonic_ms=1500), dummy_context)
    assert len(steps3) == 0

    # User presses 'A' while still holding Ctrl
    steps4 = interpreter.feed_input(RawInputEvent("key_down", key_name="A", monotonic_ms=1600), dummy_context)
    assert len(steps4) == 1
    step = steps4[0]
    assert step.action == ActionType.KEY_PRESS
    assert step.params["keys"] == ["CTRL", "A"]
    assert step.to_action_array() == ["key_press", "", "CTRL+A"]

    # User releases 'A'
    steps5 = interpreter.feed_input(RawInputEvent("key_up", key_name="a", monotonic_ms=1680), dummy_context)
    assert len(steps5) == 0

    # User releases Left Ctrl
    steps6 = interpreter.feed_input(RawInputEvent("key_up", key_name="CTRL_L", monotonic_ms=1700), dummy_context)
    assert len(steps6) == 0


def test_ctrl_shift_s_hotkey_combination(dummy_context):
    interpreter = ActionInterpreter()

    interpreter.feed_input(RawInputEvent("key_down", key_name="CTRL_L", monotonic_ms=1000), dummy_context)
    interpreter.feed_input(RawInputEvent("key_down", key_name="SHIFT_L", monotonic_ms=1050), dummy_context)
    steps = interpreter.feed_input(RawInputEvent("key_down", key_name="S", monotonic_ms=1100), dummy_context)

    assert len(steps) == 1
    assert steps[0].action == ActionType.KEY_PRESS
    assert steps[0].params["keys"] == ["CTRL", "SHIFT", "S"]
    assert steps[0].to_action_array() == ["key_press", "", "CTRL+SHIFT+S"]


def test_alt_f4_hotkey_combination(dummy_context):
    interpreter = ActionInterpreter()

    interpreter.feed_input(RawInputEvent("key_down", key_name="ALT_L", monotonic_ms=1000), dummy_context)
    steps = interpreter.feed_input(RawInputEvent("key_down", key_name="F4", monotonic_ms=1100), dummy_context)

    assert len(steps) == 1
    assert steps[0].action == ActionType.KEY_PRESS
    assert steps[0].params["keys"] == ["ALT", "F4"]
    assert steps[0].to_action_array() == ["key_press", "", "ALT+F4"]


def test_shift_tab_hotkey_combination(dummy_context):
    interpreter = ActionInterpreter()

    interpreter.feed_input(RawInputEvent("key_down", key_name="SHIFT_L", monotonic_ms=1000), dummy_context)
    steps = interpreter.feed_input(RawInputEvent("key_down", key_name="TAB", monotonic_ms=1100), dummy_context)

    assert len(steps) == 1
    assert steps[0].action == ActionType.KEY_PRESS
    assert steps[0].params["keys"] == ["SHIFT", "TAB"]
    assert steps[0].to_action_array() == ["key_press", "", "SHIFT+TAB"]


def test_shift_typing_capital_letters(dummy_context):
    """Holding Shift while typing printable characters aggregates normal typing."""
    interpreter = ActionInterpreter()

    interpreter.feed_input(RawInputEvent("key_down", key_name="SHIFT_L", monotonic_ms=1000), dummy_context)
    interpreter.feed_input(RawInputEvent("key_down", key_name="H", monotonic_ms=1050), dummy_context)
    interpreter.feed_input(RawInputEvent("key_up", key_name="SHIFT_L", monotonic_ms=1100), dummy_context)
    interpreter.feed_input(RawInputEvent("key_down", key_name="i", monotonic_ms=1150), dummy_context)

    flushed = interpreter.flush(now_ms=1300)
    assert len(flushed) == 1
    assert flushed[0].action == ActionType.TYPE
    assert flushed[0].params["text"] == "Hi"


def test_standalone_ctrl_tap_does_not_emit(dummy_context):
    """Pressing and releasing Ctrl alone without any key should not produce junk steps."""
    interpreter = ActionInterpreter()

    interpreter.feed_input(RawInputEvent("key_down", key_name="CTRL_L", monotonic_ms=1000), dummy_context)
    interpreter.feed_input(RawInputEvent("key_down", key_name="CTRL_L", monotonic_ms=1200), dummy_context)
    steps = interpreter.feed_input(RawInputEvent("key_up", key_name="CTRL_L", monotonic_ms=1300), dummy_context)

    assert len(steps) == 0
    flushed = interpreter.flush(now_ms=1400)
    assert len(flushed) == 0


def test_passive_input_format_control_chars():
    """Verify PassiveInputSource decodes ASCII control chars emitted by OS when Ctrl is held."""
    from pynput import keyboard
    from xgen.recorder.adapters.passive_input import PassiveInputSource

    # Ctrl+A -> '\x01', Ctrl+C -> '\x03', Ctrl+V -> '\x16', Ctrl+Z -> '\x1a'
    k_ctrl_a = keyboard.KeyCode(char="\x01", vk=65)
    k_ctrl_c = keyboard.KeyCode(char="\x03", vk=67)
    k_ctrl_v = keyboard.KeyCode(char="\x16", vk=86)
    k_ctrl_z = keyboard.KeyCode(char="\x1a", vk=90)

    assert PassiveInputSource._format_key(k_ctrl_a) == "A"
    assert PassiveInputSource._format_key(k_ctrl_c) == "C"
    assert PassiveInputSource._format_key(k_ctrl_v) == "V"
    assert PassiveInputSource._format_key(k_ctrl_z) == "Z"

