"""
Recorder Composition Factory.
Wires together production ports and adapters to instantiate a fully functional RecorderService.
Zero Qt dependencies.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

from xgen.recorder.adapters.jsonl_store import JsonlRecordingStore
from xgen.recorder.adapters.passive_input import PassiveInputSource
from xgen.recorder.adapters.system_clock import SystemClock
from xgen.recorder.adapters.windows_context import WindowsContextProvider
from xgen.recorder.adapters.windows_scene import WindowsSceneEventSource
from xgen.recorder.events import EventBus
from xgen.recorder.exporters.registry import default_registry
from xgen.recorder.locators.engine import LocatorEngine
from xgen.recorder.ports.clock import Clock
from xgen.recorder.ports.context import NativeContextProvider
from xgen.recorder.ports.exporter import Exporter
from xgen.recorder.ports.input_source import InputSource
from xgen.recorder.ports.scene import SceneEventSource
from xgen.recorder.ports.store import RecordingStore
from xgen.recorder.scene.cache import SceneCache
from xgen.recorder.service import RecorderService


def create_recorder(
    clock: Optional[Clock] = None,
    input_source: Optional[InputSource] = None,
    context_provider: Optional[NativeContextProvider] = None,
    store: Optional[RecordingStore] = None,
    exporters: Optional[Mapping[str, Exporter]] = None,
    locator_engine: Optional[LocatorEngine] = None,
    scene_source: Optional[SceneEventSource] = None,
    scene_cache: Optional[SceneCache] = None,
    event_bus: Optional[EventBus] = None,
    storage_dir: Optional[Path | str] = None,
) -> RecorderService:
    """
    Assembles a complete RecorderService with default Windows adapters and registered exporters.
    """
    resolved_clock = clock or SystemClock()
    resolved_input = input_source or PassiveInputSource()
    resolved_ctx = context_provider or WindowsContextProvider()
    resolved_store = store or JsonlRecordingStore(root_dir=storage_dir)
    resolved_exporters = exporters if exporters is not None else default_registry().as_dict()
    resolved_loc_engine = locator_engine or LocatorEngine()
    resolved_scene_source = scene_source or WindowsSceneEventSource()
    resolved_scene_cache = scene_cache or SceneCache()
    resolved_bus = event_bus or EventBus()

    return RecorderService(
        clock=resolved_clock,
        input_source=resolved_input,
        context_provider=resolved_ctx,
        store=resolved_store,
        exporters=resolved_exporters,
        locator_engine=resolved_loc_engine,
        scene_source=resolved_scene_source,
        scene_cache=resolved_scene_cache,
        event_bus=resolved_bus
    )
