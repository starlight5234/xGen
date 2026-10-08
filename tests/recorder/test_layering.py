"""
Layering Tests for xgen.recorder.
Strictly enforces architectural decoupling:
Nothing inside xgen.recorder may import PyQt6 or any UI framework.
"""
import sys
import subprocess
import pytest


def test_recorder_core_has_zero_qt_imports():
    """
    Subprocess test ensuring importing xgen.recorder does not pull in PyQt6.
    """
    code = """
import sys
import xgen.recorder
from xgen.recorder.models import Step, ActionType
from xgen.recorder.api import RecorderApi
from xgen.recorder.service import RecorderService
from xgen.recorder.capture.interpreter import ActionInterpreter
from xgen.recorder.events import EventBus
from xgen.recorder.adapters.system_clock import SystemClock
if sys.platform == "win32":
    from xgen.recorder.adapters.windows_context import WindowsContextProvider
from xgen.recorder.locators.engine import LocatorEngine

# Check all loaded modules
qt_modules = [m for m in sys.modules if m.startswith("PyQt") or m.startswith("PySide")]
if qt_modules:
    print(f"FAILED: Qt imported by xgen.recorder: {qt_modules}")
    sys.exit(1)

print("SUCCESS: xgen.recorder is 100% Qt-free")
sys.exit(0)
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, f"Layering violation in xgen.recorder:\n{result.stderr}\n{result.stdout}"
    assert "SUCCESS" in result.stdout
