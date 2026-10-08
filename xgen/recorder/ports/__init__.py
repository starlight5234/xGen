"""
Recorder Ports (Protocols/Interfaces).
Pure Python interfaces defining boundaries between core domain logic and adapters.
"""
from xgen.recorder.ports.clock import Clock
from xgen.recorder.ports.input_source import InputSource
from xgen.recorder.ports.context import NativeContextProvider
from xgen.recorder.ports.scene import SceneEventSource
from xgen.recorder.ports.store import RecordingStore
from xgen.recorder.ports.exporter import Exporter

__all__ = [
    "Clock",
    "InputSource",
    "NativeContextProvider",
    "SceneEventSource",
    "RecordingStore",
    "Exporter",
]
