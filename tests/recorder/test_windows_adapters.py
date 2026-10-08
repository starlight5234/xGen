"""
Unit and integration tests for Windows recorder adapters.
Verifies SystemClock, PassiveInputSource, and WindowsContextProvider.
Zero Qt dependencies.
"""
import sys
import time
import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only adapter tests")

from xgen.recorder.adapters.system_clock import SystemClock
from xgen.recorder.adapters.passive_input import PassiveInputSource
from xgen.recorder.adapters.windows_context import WindowsContextProvider
from xgen.recorder.models import RawInputEvent


def test_system_clock():
    clock = SystemClock()
    t1 = clock.monotonic_ms()
    time.sleep(0.01)
    t2 = clock.monotonic_ms()
    assert t2 >= t1

    iso = clock.wall_time_iso()
    assert isinstance(iso, str)
    assert "T" in iso


def test_passive_input_source_lifecycle_and_dispatch():
    source = PassiveInputSource()
    assert not source.is_running()

    events = []
    source.start(lambda e: events.append(e))
    assert source.is_running()

    # Manually test callback enqueueing
    mock_btn = MagicMock()
    mock_btn.name = "left"
    source._on_mouse_click(100, 200, mock_btn, True)

    # Wait for dispatcher thread to deliver event
    time.sleep(0.1)
    assert len(events) == 1
    assert events[0].kind == "mouse_down"
    assert events[0].x == 100
    assert events[0].y == 200
    assert events[0].button == "left"

    source.stop()
    assert not source.is_running()


def test_passive_input_key_formatting():
    # Character key
    mock_char_key = MagicMock()
    mock_char_key.char = "a"
    assert PassiveInputSource._format_key(mock_char_key) == "a"

    # Named special key (e.g. Key.enter)
    mock_special_key = MagicMock(spec=[])
    mock_special_key.char = None
    mock_special_key.name = "enter"
    assert PassiveInputSource._format_key(mock_special_key) == "ENTER"


def test_windows_context_provider_basic_apis():
    provider = WindowsContextProvider()
    caps = provider.capabilities()
    assert caps.has_native_accessibility is True

    # Cursor position
    cx, cy = provider.cursor_position()
    assert isinstance(cx, int)
    assert isinstance(cy, int)

    # Window still exists check (0 is not a valid window)
    assert provider.window_still_exists(0) is False

    # Same title windows count
    win_facts = MagicMock()
    win_facts.title = "NonExistentWindow_12345"
    assert provider.same_title_windows(win_facts) == 1


def test_windows_context_provider_element_facts_conversion():
    mock_ctrl = MagicMock()
    mock_ctrl.ControlTypeName = "ButtonControl"
    mock_ctrl.Name = "Submit"
    mock_ctrl.AutomationId = "btnSubmit"
    mock_ctrl.ClassName = "Button"
    mock_ctrl.HelpText = "Click to submit"
    mock_ctrl.IsPassword = False
    mock_ctrl.NativeWindowHandle = 0x1234

    mock_rect = MagicMock()
    mock_rect.left = 10
    mock_rect.top = 20
    mock_rect.right = 110
    mock_rect.bottom = 60
    mock_ctrl.BoundingRectangle = mock_rect

    facts = WindowsContextProvider._element_facts(mock_ctrl)
    assert facts.control_type == "Button"
    assert facts.name == "Submit"
    assert facts.automation_id == "btnSubmit"
    assert facts.class_name == "Button"
    assert facts.help_text == "Click to submit"
    assert facts.is_password is False
    assert facts.native_handle == 0x1234
    assert facts.bounds is not None
    assert facts.bounds.left == 10
    assert facts.bounds.top == 20
    assert facts.bounds.right == 110
    assert facts.bounds.bottom == 60


def test_windows_context_provider_context_menu_resolution():
    provider = WindowsContextProvider()

    # Target: MenuItem "Refresh" with handle 0 (standard UIA MenuItem)
    target_ctrl = MagicMock()
    target_ctrl.ControlTypeName = "MenuItemControl"
    target_ctrl.Name = "Refresh"
    target_ctrl.ClassName = ""
    target_ctrl.NativeWindowHandle = 0
    target_ctrl.ProcessId = 1234
    target_ctrl.BoundingRectangle = None

    # Ancestor: Menu "Context" with standard Win32 context menu class #32768
    menu_ctrl = MagicMock()
    menu_ctrl.ControlTypeName = "MenuControl"
    menu_ctrl.Name = "Context"
    menu_ctrl.ClassName = "#32768"
    menu_ctrl.NativeWindowHandle = 0x8000
    menu_ctrl.ProcessId = 1234
    menu_ctrl.BoundingRectangle = None

    win_facts = provider._resolve_window_facts(
        target_ctrl=target_ctrl,
        top_window_ctrl=None,
        ancestors=[menu_ctrl],
        point_hwnd=0
    )

    assert win_facts.handle == 0x8000
    assert win_facts.class_name == "#32768"
    assert win_facts.kind == "menu"
    assert win_facts.title != "Unknown Window"

    # Refine with explorer process facts
    from xgen.recorder.models import ProcessFacts
    proc_explorer = ProcessFacts(pid=1234, exe_name="explorer.exe", app_name="explorer")
    refined_explorer = provider._refine_window_title(win_facts, proc_explorer)
    assert refined_explorer.title == "Desktop Context Menu"

    # Refine with arbitrary application process facts
    proc_notepad = ProcessFacts(pid=5678, exe_name="notepad.exe", app_name="notepad")
    refined_notepad = provider._refine_window_title(win_facts, proc_notepad)
    assert refined_notepad.title == "Context Menu (notepad)"


def test_windows_context_provider_popup_dropdown_resolution():
    provider = WindowsContextProvider()

    target_ctrl = MagicMock()
    target_ctrl.ControlTypeName = "ListItemControl"
    target_ctrl.Name = "Option A"
    target_ctrl.ClassName = ""
    target_ctrl.NativeWindowHandle = 0
    target_ctrl.ProcessId = 2222
    target_ctrl.BoundingRectangle = None

    popup_ctrl = MagicMock()
    popup_ctrl.ControlTypeName = "PaneControl"
    popup_ctrl.Name = ""
    popup_ctrl.ClassName = "ComboLBox"
    popup_ctrl.NativeWindowHandle = 0x9000
    popup_ctrl.ProcessId = 2222
    popup_ctrl.BoundingRectangle = None

    win_facts = provider._resolve_window_facts(
        target_ctrl=target_ctrl,
        top_window_ctrl=None,
        ancestors=[popup_ctrl],
        point_hwnd=0
    )

    assert win_facts.handle == 0x9000
    assert win_facts.class_name == "ComboLBox"
    assert win_facts.kind == "popup"
    assert win_facts.title != "Unknown Window"

    from xgen.recorder.models import ProcessFacts
    proc = ProcessFacts(pid=2222, exe_name="chrome.exe", app_name="chrome")
    refined = provider._refine_window_title(win_facts, proc)
    assert refined.title == "Popup (chrome)"

