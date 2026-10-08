"""
xGen Recorder Core Package.
Headless, modular, and decoupled from GUI/Qt.
"""
from xgen.recorder.models import (
    ActionType, Bounds, CapturedContext, ElementChain, ElementFacts,
    ExportResult, ExporterInfo, LocatorCandidate, LocatorState,
    PagedSteps, ProcessFacts, RawInputEvent, RecorderState, Recording,
    RecordingMeta, RecordingStatus, ResolutionMethod, Step, WindowFacts
)
from xgen.recorder.api import RecorderApi, RecorderError, RecorderErrorCode
from xgen.recorder.options import (
    CaptureOptions, PlaybackOptions, RecordingOptions, RedactionRule,
    TargetScopeOptions
)
from xgen.recorder.service import RecorderService
from xgen.recorder.events import EventBus, RecorderEvent
from xgen.recorder.composition import create_recorder
from xgen.recorder.playback import PlaybackRunner, PlaybackResult

__all__ = [
    "ActionType",
    "Bounds",
    "CapturedContext",
    "ElementChain",
    "ElementFacts",
    "ExportResult",
    "ExporterInfo",
    "LocatorCandidate",
    "LocatorState",
    "PagedSteps",
    "ProcessFacts",
    "RawInputEvent",
    "RecorderState",
    "Recording",
    "RecordingMeta",
    "RecordingStatus",
    "ResolutionMethod",
    "Step",
    "WindowFacts",
    "RecorderApi",
    "RecorderError",
    "RecorderErrorCode",
    "CaptureOptions",
    "PlaybackOptions",
    "RecordingOptions",
    "RedactionRule",
    "TargetScopeOptions",
    "RecorderService",
    "EventBus",
    "RecorderEvent",
    "create_recorder",
    "PlaybackRunner",
    "PlaybackResult",
]
