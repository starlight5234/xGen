"""
Recorder Service.
Core coordinator implementing RecorderApi by composing ports, ActionInterpreter, and EventBus.
Zero Qt dependencies.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Callable, Dict, List, Mapping, Optional

from xgen.recorder.api import RecorderApi, RecorderError, RecorderErrorCode
from xgen.recorder.capture.interpreter import ActionInterpreter
from xgen.recorder.events import (
    ErrorEvent, EventBus, RecorderEvent, StateChangedEvent, StepDeletedEvent,
    StepRecordedEvent, StepUpdatedEvent, WarningEvent
)
from xgen.recorder.locators.engine import LocatorEngine
from xgen.recorder.models import (
    ActionType, CapturedContext, ExportResult, ExporterInfo, LocatorCandidate, LocatorState,
    PagedSteps, RawInputEvent, Recording, RecordingMeta, RecordingStatus, RecorderState,
    ResolutionMethod, SceneEvent, Step
)
from xgen.recorder.options import RecordingOptions
from xgen.recorder.ports.clock import Clock
from xgen.recorder.ports.context import NativeContextProvider
from xgen.recorder.ports.exporter import Exporter
from xgen.recorder.ports.input_source import InputSource
from xgen.recorder.ports.scene import SceneEventSource
from xgen.recorder.ports.store import RecordingStore
from xgen.recorder.scene.cache import SceneCache
from xgen.recorder.exporters.registry import default_registry
from xgen.recorder.verification import VerificationRunner

logger = logging.getLogger("xgen.recorder.service")


class RecorderService(RecorderApi):
    """
    Coordinates recording session lifecycle, input consumption, storage, and exporting.
    """
    def __init__(self,
                 clock: Clock,
                 input_source: InputSource,
                 context_provider: NativeContextProvider,
                 store: RecordingStore,
                 exporters: Optional[Mapping[str, Exporter]] = None,
                 locator_engine: Optional[LocatorEngine] = None,
                 scene_source: Optional[SceneEventSource] = None,
                 scene_cache: Optional[SceneCache] = None,
                 event_bus: Optional[EventBus] = None,
                 verification_runner: Optional[VerificationRunner] = None):
        self.clock = clock
        self.input_source = input_source
        self.context_provider = context_provider
        self.store = store
        self.exporters: Dict[str, Exporter] = dict(exporters) if exporters is not None else default_registry().as_dict()
        self.locator_engine = locator_engine or LocatorEngine()
        self.scene_source = scene_source
        self.scene_cache = scene_cache or SceneCache()
        self.event_bus = event_bus or EventBus()
        self.verification_runner = verification_runner or VerificationRunner(event_bus=self.event_bus, store=self.store)

        self._lock = threading.RLock()
        self._state = RecorderState.IDLE
        self._active_recording: Optional[Recording] = None
        self._last_completed_recording: Optional[Recording] = None
        self._interpreter: Optional[ActionInterpreter] = None
        self._options: Optional[RecordingOptions] = None
        self._start_mono_ms: int = 0
        self._last_window_handle: int = 0

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self, options: Optional[RecordingOptions] = None) -> str:
        with self._lock:
            if self._state not in (RecorderState.IDLE, RecorderState.ERROR):
                raise RecorderError(RecorderErrorCode.INVALID_STATE, f"Cannot start recording while in {self._state.value} state")

            self._set_state(RecorderState.STARTING)
            opts = options or RecordingOptions()
            self._options = opts
            self._last_window_handle = 0
            rec_id = str(uuid.uuid4())
            now_iso = self.clock.wall_time_iso()
            self._start_mono_ms = self.clock.monotonic_ms()

            meta = RecordingMeta(
                id=rec_id,
                name=opts.name,
                dialect_key=opts.dialect_key,
                started_at=now_iso
            )
            self._active_recording = Recording(meta=meta, steps=[])
            self._last_completed_recording = None
            self.store.create(meta)

            self._interpreter = ActionInterpreter(
                options=opts.capture,
                on_step=self._on_step_produced
            )

            try:
                if self.scene_source:
                    self.scene_source.start(self._on_scene_event)
                self.input_source.start(self._on_raw_input)
                self._set_state(RecorderState.RECORDING)
                return rec_id
            except Exception as e:
                if self.scene_source:
                    try:
                        self.scene_source.stop()
                    except Exception:
                        pass
                self._set_state(RecorderState.ERROR)
                raise RecorderError(RecorderErrorCode.HOOK_FAILED, f"Failed to start input listener: {e}")

    def pause(self) -> None:
        with self._lock:
            if self._state != RecorderState.RECORDING:
                raise RecorderError(RecorderErrorCode.INVALID_STATE, f"Cannot pause while in {self._state.value} state")
            self._set_state(RecorderState.PAUSED)

    def resume(self) -> None:
        with self._lock:
            if self._state != RecorderState.PAUSED:
                raise RecorderError(RecorderErrorCode.INVALID_STATE, f"Cannot resume while in {self._state.value} state")
            self._set_state(RecorderState.RECORDING)

    def stop(self) -> RecordingMeta:
        with self._lock:
            if self._state not in (RecorderState.RECORDING, RecorderState.PAUSED):
                raise RecorderError(RecorderErrorCode.INVALID_STATE, f"Cannot stop while in {self._state.value} state")

            self._set_state(RecorderState.STOPPING)
            if self.scene_source:
                try:
                    self.scene_source.stop()
                except Exception as e:
                    logger.debug("Error stopping scene source: %s", e)
            if self.input_source.is_running():
                self.input_source.stop()

            interpreter = self._interpreter

        # Flush any pending typing from the interpreter outside the lock
        if interpreter:
            interpreter.flush(self.clock.monotonic_ms())

        with self._lock:
            assert self._active_recording is not None
            rec = self._active_recording
            now_iso = self.clock.wall_time_iso()
            elapsed_sec = (self.clock.monotonic_ms() - self._start_mono_ms) / 1000.0

            rec.meta.stopped_at = now_iso
            rec.meta.step_count = len(rec.steps)
            rec.meta.duration_seconds = round(elapsed_sec, 2)

            self.store.finalize(rec)
            meta = rec.meta

            self._last_completed_recording = rec
            self._active_recording = None
            self._set_state(RecorderState.IDLE)
            return meta

    def status(self) -> RecordingStatus:
        with self._lock:
            is_active = self._state in (RecorderState.RECORDING, RecorderState.PAUSED)
            rec_id = self._active_recording.meta.id if (self._active_recording and is_active) else None
            count = len(self._active_recording.steps) if (self._active_recording and is_active) else 0
            dur = (self.clock.monotonic_ms() - self._start_mono_ms) / 1000.0 if is_active else 0.0
            return RecordingStatus(
                state=self._state,
                recording_id=rec_id,
                step_count=count,
                duration_seconds=round(dur, 2)
            )

    # -------------------------------------------------------------------------
    # Steps & Timeline
    # -------------------------------------------------------------------------

    def get_steps(self, since_seq: int = 0, limit: int = 100) -> PagedSteps:
        with self._lock:
            rec = self._active_recording or self._last_completed_recording
            if not rec:
                recs = self.store.list()
                if recs:
                    try:
                        rec = self.store.load(recs[0].id)
                        self._last_completed_recording = rec
                    except Exception as e:
                        logger.debug("Failed to load latest recording from store: %s", e)
            if not rec:
                return PagedSteps(steps=[], total_count=0, has_more=False)
            filtered = [s for s in rec.steps if s.seq > since_seq]
            paged = filtered[:limit]
            has_more = len(filtered) > limit
            return PagedSteps(steps=paged, total_count=len(rec.steps), has_more=has_more)

    def get_step(self, step_id: str) -> Step:
        with self._lock:
            if self._active_recording:
                for s in self._active_recording.steps:
                    if s.id == step_id:
                        return s
                raise RecorderError(RecorderErrorCode.STEP_NOT_FOUND, f"Step '{step_id}' not found")

            rec = self._last_completed_recording
            if not rec:
                recs = self.store.list()
                if recs:
                    try:
                        rec = self.store.load(recs[0].id)
                        self._last_completed_recording = rec
                    except Exception:
                        pass
            if rec:
                for s in rec.steps:
                    if s.id == step_id:
                        return s

            recs = self.store.list()
            for r_meta in recs:
                try:
                    candidate = self.store.load(r_meta.id)
                    for s in candidate.steps:
                        if s.id == step_id:
                            self._last_completed_recording = candidate
                            return s
                except Exception:
                    pass
            raise RecorderError(RecorderErrorCode.STEP_NOT_FOUND, f"Step '{step_id}' not found")

    def update_step(self, step_id: str, patch: Mapping[str, Any]) -> Step:
        with self._lock:
            step = self.get_step(step_id)
            if "notes" in patch:
                step.notes = str(patch["notes"])
            if "params" in patch and isinstance(patch["params"], dict):
                step.params.update(patch["params"])
            if "flags" in patch and isinstance(patch["flags"], list):
                step.flags = list(patch["flags"])

            if self._active_recording:
                self.event_bus.publish(StepUpdatedEvent(recording_id=self._active_recording.meta.id, step=step))
            elif self._last_completed_recording:
                self.store.finalize(self._last_completed_recording)
                self.event_bus.publish(StepUpdatedEvent(recording_id=self._last_completed_recording.meta.id, step=step))
            return step

    def delete_step(self, step_id: str) -> bool:
        with self._lock:
            # 1. Check active in-memory recording first
            if self._active_recording:
                for i, s in enumerate(self._active_recording.steps):
                    if s.id == step_id:
                        self._active_recording.steps.pop(i)
                        for idx, st in enumerate(self._active_recording.steps):
                            st.seq = idx + 1
                        self._active_recording.meta.step_count = len(self._active_recording.steps)
                        self.event_bus.publish(StepDeletedEvent(recording_id=self._active_recording.meta.id, step_id=step_id))
                        return True
                return False

            # 2. Check last completed recording
            if self._last_completed_recording:
                for i, s in enumerate(self._last_completed_recording.steps):
                    if s.id == step_id:
                        self._last_completed_recording.steps.pop(i)
                        for idx, st in enumerate(self._last_completed_recording.steps):
                            st.seq = idx + 1
                        self._last_completed_recording.meta.step_count = len(self._last_completed_recording.steps)
                        self.store.finalize(self._last_completed_recording)
                        self.event_bus.publish(StepDeletedEvent(recording_id=self._last_completed_recording.meta.id, step_id=step_id))
                        return True

            # 3. Fallback: Search all saved recordings in the store
            recs = self.store.list()
            for r_meta in recs:
                try:
                    candidate = self.store.load(r_meta.id)
                    for i, s in enumerate(candidate.steps):
                        if s.id == step_id:
                            candidate.steps.pop(i)
                            for idx, st in enumerate(candidate.steps):
                                st.seq = idx + 1
                            candidate.meta.step_count = len(candidate.steps)
                            self.store.finalize(candidate)
                            self._last_completed_recording = candidate
                            self.event_bus.publish(StepDeletedEvent(recording_id=candidate.meta.id, step_id=step_id))
                            return True
                except Exception as e:
                    logger.debug("Error inspecting recording %s during delete: %s", r_meta.id, e)

            return False

    def restore_step(self, step: Step, index: Optional[int] = None) -> bool:
        """Restore a previously deleted step back into the active or completed recording."""
        with self._lock:
            rec = self._active_recording or self._last_completed_recording
            if not rec:
                recs = self.store.list()
                if recs:
                    try:
                        rec = self.store.load(recs[0].id)
                        self._last_completed_recording = rec
                    except Exception:
                        pass
            if not rec:
                return False

            if index is not None and 0 <= index <= len(rec.steps):
                rec.steps.insert(index, step)
            else:
                rec.steps.append(step)

            for idx, st in enumerate(rec.steps):
                st.seq = idx + 1
            rec.meta.step_count = len(rec.steps)

            if not self._active_recording:
                self.store.finalize(rec)
            return True

    def clear_steps(self) -> bool:
        with self._lock:
            rec = self._active_recording or self._last_completed_recording
            if not rec:
                recs = self.store.list()
                if recs:
                    try:
                        rec = self.store.load(recs[0].id)
                        self._last_completed_recording = rec
                    except Exception:
                        pass
            if not rec:
                return False
            rec_id = rec.meta.id
            step_ids = [s.id for s in rec.steps]
            rec.steps.clear()
            rec.meta.step_count = 0
            if self._active_recording:
                for sid in step_ids:
                    self.event_bus.publish(StepDeletedEvent(recording_id=rec_id, step_id=sid))
            else:
                self.store.finalize(rec)
            return True

    def select_locator(self, step_id: str, locator_index: int) -> Step:
        with self._lock:
            step = self.get_step(step_id)
            if not (0 <= locator_index < len(step.locators)):
                raise RecorderError(RecorderErrorCode.INVALID_ARGUMENT, f"Locator index {locator_index} out of range")
            step.selected_locator = locator_index
            if self._active_recording:
                self.event_bus.publish(StepUpdatedEvent(recording_id=self._active_recording.meta.id, step=step))
            elif self._last_completed_recording:
                self.store.finalize(self._last_completed_recording)
                self.event_bus.publish(StepUpdatedEvent(recording_id=self._last_completed_recording.meta.id, step=step))
            return step

    # -------------------------------------------------------------------------
    # Inspection
    # -------------------------------------------------------------------------

    def inspect_at_cursor(self) -> Optional[Step]:
        cx, cy = self.context_provider.cursor_position()
        ctx = self.context_provider.capture_at(cx, cy, deadline_ms=100)
        if not ctx:
            return None
        return Step(
            id=str(uuid.uuid4()),
            seq=0,
            action=ActionType.ASSERT,
            created_at=self.clock.wall_time_iso(),
            monotonic_ms=self.clock.monotonic_ms(),
            process=ctx.chain.process,
            window=ctx.chain.window,
            target=ctx.chain,
            params={"point": {"x": cx, "y": cy}},
            resolution=ctx.resolution
        )

    # -------------------------------------------------------------------------
    # Storage & History
    # -------------------------------------------------------------------------

    def get_recording(self, recording_id: str) -> Recording:
        with self._lock:
            if self._active_recording and self._active_recording.meta.id == recording_id and self._state in (RecorderState.RECORDING, RecorderState.PAUSED):
                return self._active_recording
            try:
                return self.store.load(recording_id)
            except KeyError as e:
                raise RecorderError(RecorderErrorCode.RECORDING_NOT_FOUND, f"Recording session '{recording_id}' not found") from e

    def list_recordings(self) -> List[RecordingMeta]:
        return self.store.list()

    def list_incomplete_recordings(self) -> List[RecordingMeta]:
        if hasattr(self.store, "incomplete"):
            return self.store.incomplete()
        return []

    def delete_recording(self, recording_id: str) -> None:
        self.store.delete(recording_id)

    # -------------------------------------------------------------------------
    # Exporters & Output
    # -------------------------------------------------------------------------

    def list_exporters(self) -> List[ExporterInfo]:
        return [
            ExporterInfo(id=exp.id, display_name=exp.display_name, file_extension=exp.file_extension)
            for exp in self.exporters.values()
        ]

    def export(self, recording_id: str, exporter_id: str = "action_xpath_json",
               options: Optional[Mapping[str, Any]] = None) -> ExportResult:
        exporter = self.exporters.get(exporter_id)
        if not exporter:
            raise RecorderError(RecorderErrorCode.EXPORTER_NOT_FOUND, f"Exporter '{exporter_id}' not found")
        rec = self.get_recording(recording_id)
        return exporter.export(rec, options or {})

    # -------------------------------------------------------------------------
    # Verification
    # -------------------------------------------------------------------------

    def start_verification(self, recording_id: str, driver: Any = None) -> str:
        rec = self.get_recording(recording_id)
        return self.verification_runner.start_job(rec, driver=driver)

    def get_verification_job(self, job_id: str) -> Optional[Any]:
        return self.verification_runner.get_job(job_id)

    def cancel_verification_job(self, job_id: str) -> bool:
        return self.verification_runner.cancel_job(job_id)

    # -------------------------------------------------------------------------
    # Event Subscriptions
    # -------------------------------------------------------------------------

    def subscribe(self, listener: Callable[[Any], None]) -> Callable[[], None]:
        return self.event_bus.subscribe(RecorderEvent, listener)

    # -------------------------------------------------------------------------
    # Internal Handlers
    # -------------------------------------------------------------------------

    def _set_state(self, new_state: RecorderState) -> None:
        old_state = self._state
        self._state = new_state
        rec_id = self._active_recording.meta.id if self._active_recording else ""
        self.event_bus.publish(StateChangedEvent(old_state=old_state, new_state=new_state, recording_id=rec_id))

    def _is_scope_allowed(self, ctx: CapturedContext) -> bool:
        if not self._options:
            return True
        scope = self._options.target_scope
        proc = ctx.chain.process
        win = ctx.chain.window

        # Check PID exclusion (e.g. self-exclusion)
        if proc.pid and proc.pid in scope.exclude_pids:
            return False

        # Check Process Name exclusion
        proc_name = proc.exe_name or proc.app_name
        if proc_name:
            proc_name_lower = proc_name.lower()
            if any(proc_name_lower == ex.lower() or proc_name_lower == f"{ex.lower()}.exe" for ex in scope.exclude_process_names):
                return False

        # Check PID inclusion
        if scope.include_pids and proc.pid not in scope.include_pids:
            return False

        # Check Process Name inclusion
        if scope.include_process_names:
            proc_name = proc.exe_name or proc.app_name or ""
            if not proc_name:
                return False
            proc_name_lower = proc_name.lower()
            if not any(proc_name_lower == inc.lower() or proc_name_lower == f"{inc.lower()}.exe" for inc in scope.include_process_names):
                return False

        # Check Window Title regex
        if scope.include_window_titles_regex and win.title:
            import re
            matched = any(re.search(pat, win.title, re.IGNORECASE) for pat in scope.include_window_titles_regex)
            if not matched:
                return False

        return True

    def get_last_recording_meta(self) -> Optional[RecordingMeta]:
        """Retrieve metadata of the most recent recording session."""
        with self._lock:
            if self._last_completed_recording:
                return self._last_completed_recording.meta
            if self._active_recording:
                return self._active_recording.meta
        recordings = self.list_recordings()
        if not recordings:
            return None
        recordings.sort(
            key=lambda r: getattr(r, "started_at_iso", "") or getattr(r, "started_at", "") or "",
            reverse=True
        )
        return recordings[0]

    def _on_raw_input(self, event: RawInputEvent) -> None:
        with self._lock:
            if self._state != RecorderState.RECORDING or not self._interpreter:
                return
            interpreter = self._interpreter

        ctx = None
        if event.kind == "mouse_down":
            ctx = self.context_provider.capture_at(event.x, event.y, deadline_ms=250)
            if not ctx and self.scene_cache:
                ctx = self.scene_cache.find_at_point(event.x, event.y)
        elif event.kind == "mouse_up":
            # If mouse_down failed to capture context (e.g. transient window just opening), capture on mouse_up
            pending = getattr(interpreter, "_pending_down", None)
            if pending and pending[1] is None:
                ctx = self.context_provider.capture_at(event.x, event.y, deadline_ms=250)
                if not ctx and self.scene_cache:
                    ctx = self.scene_cache.find_at_point(event.x, event.y)
        elif event.kind == "key_down":
            ctx = self.context_provider.capture_focused(deadline_ms=250)

        if ctx and not self._is_scope_allowed(ctx):
            return

        wall_time = self.clock.wall_time_iso()
        interpreter.feed_input(event, ctx, wall_time_iso=wall_time)

    def _on_scene_event(self, event: SceneEvent) -> None:
        with self._lock:
            if self._state != RecorderState.RECORDING or not self.scene_source or not self.scene_cache:
                return
            scene_source = self.scene_source
            scene_cache = self.scene_cache

        try:
            snap = scene_source.snapshot(event.window_handle, deadline_ms=200)
            if snap:
                scene_cache.put_snapshot(snap)
        except Exception as e:
            logger.debug("Failed to handle scene event: %s", e)

    def _build_fallback_locator(self, step: Step) -> Optional[LocatorCandidate]:
        from xgen.utils.xpath_escape import escape_xpath_literal
        win = step.window
        if win and win.title:
            val = escape_xpath_literal(win.title)
            return LocatorCandidate(
                xpath=f"//Window[@Name={val}]",
                tier="fallback",
                stability_score=35,
                state=LocatorState.UNVERIFIED,
                notes=["fallback_window_title"]
            )
        if win and win.class_name:
            val = escape_xpath_literal(win.class_name)
            return LocatorCandidate(
                xpath=f"//Window[@ClassName={val}]",
                tier="fallback",
                stability_score=30,
                state=LocatorState.UNVERIFIED,
                notes=["fallback_window_class"]
            )
        if win and win.kind == "popup":
            return LocatorCandidate(
                xpath="//*[contains(@ClassName, 'Popup') or @ClassName='#32768']",
                tier="fallback",
                stability_score=25,
                state=LocatorState.UNVERIFIED,
                notes=["fallback_popup_class"]
            )
        return LocatorCandidate(
            xpath="/*",
            tier="fallback",
            stability_score=10,
            state=LocatorState.UNVERIFIED,
            notes=["fallback_root"]
        )

    def _on_step_produced(self, step: Step) -> None:
        # Fallback post-gesture resolution for fast/popup windows if step.target was not resolved yet
        if not step.target and step.params and "x" in step.params and "y" in step.params:
            try:
                px, py = int(step.params["x"]), int(step.params["y"])
                post_ctx = self.context_provider.capture_at(px, py, deadline_ms=200)
                if not post_ctx and self.scene_cache:
                    post_ctx = self.scene_cache.find_at_point(px, py)
                if post_ctx:
                    step.target = post_ctx.chain
                    step.resolution = post_ctx.resolution
                    if (not step.window or step.window.handle == 0) and post_ctx.chain.window:
                        step.window = post_ctx.chain.window
                    if (not step.process or step.process.pid == 0) and post_ctx.chain.process:
                        step.process = post_ctx.chain.process
            except Exception as e:
                logger.debug("Post-gesture context capture fallback failed: %s", e)

        # Generate and rank XPath locators if target context is available (outside lock)
        if step.target:
            try:
                ctx = CapturedContext(
                    chain=step.target,
                    resolution=step.resolution,
                    captured_at_ms=step.monotonic_ms,
                    snapshot_cost_ms=0
                )
                similar = self.context_provider.find_similar(ctx, limit=10, deadline_ms=80)
                step.locators = self.locator_engine.generate_locators(ctx, similar)
                if step.locators:
                    step.selected_locator = 0
                    step.locator_state = step.locators[0].state
            except Exception as e:
                logger.debug("Failed to synthesize locators for step %s: %s", step.id, e)
                step.flags.append(f"synthesis_error: {e}")

        # Ensure step has at least a resilient window/container fallback locator if still unassigned
        if not step.locators and step.action != ActionType.SWITCH_WINDOW:
            fallback = self._build_fallback_locator(step)
            if fallback:
                step.locators = [fallback]
                step.selected_locator = 0
                step.locator_state = fallback.state

        with self._lock:
            if not self._active_recording:
                return

            # Check for top-level window switch (menus and popups do not switch top-level window)
            curr_hwnd = step.window.handle if step.window else 0
            is_main_win = bool(step.window and step.window.kind in ("main", "dialog"))
            if is_main_win and self._last_window_handle != 0 and curr_hwnd != 0 and curr_hwnd != self._last_window_handle:
                switch_step = Step(
                    id=str(uuid.uuid4()),
                    seq=len(self._active_recording.steps) + 1,
                    action=ActionType.SWITCH_WINDOW,
                    created_at=step.created_at,
                    monotonic_ms=step.monotonic_ms,
                    process=step.process,
                    window=step.window,
                    params={
                        "to_window": step.window.to_dict(),
                        "title": step.window.title
                    },
                    resolution=ResolutionMethod.NATIVE_EXACT
                )
                self._active_recording.steps.append(switch_step)
                self._active_recording.meta.step_count = len(self._active_recording.steps)
                try:
                    self.store.append_step(self._active_recording.meta.id, switch_step)
                except Exception as e:
                    logger.debug("Failed to store switch_window step: %s", e)
                self.event_bus.publish(StepRecordedEvent(recording_id=self._active_recording.meta.id, step=switch_step))

            if curr_hwnd != 0 and is_main_win:
                self._last_window_handle = curr_hwnd

            # Re-index step sequence
            step.seq = len(self._active_recording.steps) + 1

            self._active_recording.steps.append(step)
            self._active_recording.meta.step_count = len(self._active_recording.steps)
            try:
                self.store.append_step(self._active_recording.meta.id, step)
            except Exception as e:
                logger.error("Failed to append step to store: %s", e)
                self.event_bus.publish(ErrorEvent(code="store_write_error", message=str(e), recording_id=self._active_recording.meta.id))
            self.event_bus.publish(StepRecordedEvent(recording_id=self._active_recording.meta.id, step=step))
