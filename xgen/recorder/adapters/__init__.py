"""
Recorder Adapters.
Implementations of ports for clock, input sources, context providers, and persistence.
"""
from xgen.recorder.adapters.system_clock import SystemClock
from xgen.recorder.adapters.passive_input import PassiveInputSource
from xgen.recorder.adapters.windows_context import WindowsContextProvider

__all__ = [
    "SystemClock",
    "PassiveInputSource",
    "WindowsContextProvider",
]
