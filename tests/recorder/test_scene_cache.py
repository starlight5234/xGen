"""
Unit tests for SceneCache and scene-driven popup resolution.
"""
from __future__ import annotations

import time
import pytest

from xgen.recorder.models import (
    Bounds, ElementFacts, ProcessFacts, RawInputEvent, ResolutionMethod,
    SceneEvent, SceneSnapshotFacts, WindowFacts
)
from xgen.recorder.scene.cache import SceneCache
from xgen.recorder.service import RecorderService
from tests.recorder.fakes import (
    FakeClock, FakeContextProvider, FakeInputSource, FakeSceneEventSource,
    InMemoryRecordingStore
)


def test_scene_cache_hit_test():
    cache = SceneCache(ttl_seconds=1.0)
    win = WindowFacts(handle=0x5000, title="Dropdown", class_name="Menu", bounds=Bounds(100, 100, 300, 400))
    el1 = ElementFacts(control_type="Menu", bounds=Bounds(100, 100, 300, 400))
    el2 = ElementFacts(control_type="MenuItem", name="Save As...", bounds=Bounds(110, 150, 290, 190))
    snap = SceneSnapshotFacts(
        window=win,
        elements=(el1, el2),
        captured_at_ms=int(time.monotonic() * 1000)
    )

    cache.put_snapshot(snap)
    assert cache.count() == 1

    # Hit test inside MenuItem
    ctx = cache.find_at_point(150, 170)
    assert ctx is not None
    assert ctx.resolution == ResolutionMethod.SCENE_CACHE
    assert ctx.chain.target.name == "Save As..."
    assert ctx.chain.target.control_type == "MenuItem"

    # Hit test outside window bounds
    assert cache.find_at_point(50, 50) is None


def test_scene_cache_expiration():
    cache = SceneCache(ttl_seconds=0.05)
    win = WindowFacts(handle=0x5000, title="Transient", class_name="Popup", bounds=Bounds(0, 0, 100, 100))
    el = ElementFacts(control_type="Button", name="OK", bounds=Bounds(10, 10, 90, 90))
    snap = SceneSnapshotFacts(window=win, elements=(el,), captured_at_ms=int(time.monotonic() * 1000))

    cache.put_snapshot(snap)
    assert cache.find_at_point(50, 50) is not None

    time.sleep(0.06)
    assert cache.find_at_point(50, 50) is None
    assert cache.count() == 0


def test_service_scene_cache_fallback():
    clock = FakeClock()
    inputs = FakeInputSource()
    ctx_provider = FakeContextProvider()
    store = InMemoryRecordingStore()
    scene_source = FakeSceneEventSource()
    scene_cache = SceneCache(ttl_seconds=5.0)

    service = RecorderService(
        clock=clock,
        input_source=inputs,
        context_provider=ctx_provider,
        store=store,
        scene_source=scene_source,
        scene_cache=scene_cache
    )

    # Prepare popup snapshot in scene_source
    popup_handle = 0x8888
    win = WindowFacts(handle=popup_handle, title="ContextMenu", class_name="Menu", bounds=Bounds(200, 200, 400, 400))
    item = ElementFacts(control_type="MenuItem", name="Paste", bounds=Bounds(210, 250, 390, 290))
    scene_source.set_snapshot(popup_handle, SceneSnapshotFacts(
        window=win,
        elements=(item,),
        captured_at_ms=1000
    ))

    # Override ctx_provider capture_at to return None for (250, 270) simulating element vanishing
    ctx_provider.capture_at = lambda x, y, deadline_ms: None

    service.start()
    assert scene_source.is_running()

    # Emit menu open scene event
    scene_source.emit_event(SceneEvent(
        kind="menu_open",
        window_handle=popup_handle,
        title="ContextMenu",
        monotonic_ms=1010
    ))

    # Click on the menu item location
    inputs.emit_event(RawInputEvent(kind="mouse_down", x=250, y=270, button="left", monotonic_ms=1020))
    inputs.emit_event(RawInputEvent(kind="mouse_up", x=250, y=270, button="left", monotonic_ms=1030))

    # Stop service
    service.stop()
    assert not scene_source.is_running()

    steps = service.get_steps().steps
    assert len(steps) == 1
    assert steps[0].action.value == "click"
    assert steps[0].resolution == ResolutionMethod.SCENE_CACHE
    assert steps[0].target is not None
    assert steps[0].target.target.name == "Paste"
