"""
Action Interpreter.
Pure algorithmic state machine converting raw mouse/keyboard events into high-level Steps.
Zero OS hooks or GUI dependencies.
"""
from __future__ import annotations

import math
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from xgen.recorder.models import (
    ActionType, CapturedContext, ElementChain, ProcessFacts,
    RawInputEvent, ResolutionMethod, Step, WindowFacts
)
from xgen.recorder.options import CaptureOptions


MODIFIER_MAP: Dict[str, str] = {
    "CTRL": "CTRL",
    "CTRL_L": "CTRL",
    "CTRL_R": "CTRL",
    "CONTROL": "CTRL",
    "CONTROL_L": "CTRL",
    "CONTROL_R": "CTRL",
    "ALT": "ALT",
    "ALT_L": "ALT",
    "ALT_R": "ALT",
    "ALT_GR": "ALT",
    "SHIFT": "SHIFT",
    "SHIFT_L": "SHIFT",
    "SHIFT_R": "SHIFT",
    "CMD": "WIN",
    "CMD_L": "WIN",
    "CMD_R": "WIN",
    "WIN": "WIN",
    "WINDOWS": "WIN",
}


class ActionInterpreter:
    """
    Transforms raw stream of RawInputEvent objects into semantic Steps.
    Handles mouse click/double-click debounce, drag detection, and typing aggregation.
    """
    def __init__(self, options: Optional[CaptureOptions] = None,
                 on_step: Optional[Callable[[Step], None]] = None):
        self.options = options or CaptureOptions()
        self.on_step = on_step
        self._seq = 0

        # Mouse tracking state
        self._pending_down: Optional[Tuple[RawInputEvent, Optional[CapturedContext]]] = None
        self._last_click: Optional[Tuple[int, int, str, int]] = None  # (x, y, button, monotonic_ms)

        # Typing aggregation state
        self._pending_text: List[str] = []
        self._pending_type_target: Optional[CapturedContext] = None
        self._pending_type_wall_time: str = ""
        self._pending_type_mono_ms: int = 0
        self._last_key_mono_ms: int = 0

        # Active modifier and hotkey tracking
        self._active_modifiers: set[str] = set()
        self._modifier_used_in_combo: bool = False
        self._modifier_context: Optional[CapturedContext] = None
        self._modifier_wall_time: str = ""
        self._modifier_mono_ms: int = 0
        self._pressed_keys: set[str] = set()

    def feed_input(self, event: RawInputEvent, ctx: Optional[CapturedContext] = None,
                   wall_time_iso: str = "") -> List[Step]:
        """
        Feed a raw input event and its resolved context at the event moment.
        Returns any steps produced immediately.
        """
        produced_steps: List[Step] = []

        if event.kind == "mouse_down":
            # If we were aggregating keystrokes, a mouse click flushes pending text
            flush_step = self._flush_typing(event.monotonic_ms)
            if flush_step:
                produced_steps.append(flush_step)
            self._pending_down = (event, ctx)

        elif event.kind == "mouse_up":
            if self._pending_down:
                down_event, down_ctx = self._pending_down
                self._pending_down = None
                step = self._resolve_mouse_gesture(down_event, event, down_ctx or ctx, wall_time_iso)
                if step:
                    produced_steps.append(step)

        elif event.kind == "key_down":
            steps = self._handle_key_down(event, ctx, wall_time_iso)
            produced_steps.extend(steps)

        elif event.kind == "key_up":
            steps = self._handle_key_up(event, ctx, wall_time_iso)
            produced_steps.extend(steps)

        elif event.kind == "scroll":
            flush_step = self._flush_typing(event.monotonic_ms)
            if flush_step:
                produced_steps.append(flush_step)
            step = self._resolve_scroll(event, ctx, wall_time_iso)
            if step:
                produced_steps.append(step)

        for s in produced_steps:
            if self.on_step:
                self.on_step(s)

        return produced_steps

    def flush(self, now_ms: int = 0) -> List[Step]:
        """Flush any pending aggregated typing buffer."""
        produced = []
        step = self._flush_typing(now_ms)
        if step:
            produced.append(step)
            if self.on_step:
                self.on_step(step)
        return produced

    def _resolve_mouse_gesture(self, down_event: RawInputEvent, up_event: RawInputEvent,
                               ctx: Optional[CapturedContext], wall_time_iso: str) -> Optional[Step]:
        dist = math.hypot(up_event.x - down_event.x, up_event.y - down_event.y)
        if dist > self.options.drag_threshold_px:
            # Drag and drop
            self._seq += 1
            return self._build_step(
                action=ActionType.DRAG_DROP,
                wall_time_iso=wall_time_iso,
                monotonic_ms=up_event.monotonic_ms,
                ctx=ctx,
                params={
                    "from_x": down_event.x, "from_y": down_event.y,
                    "to_x": up_event.x, "to_y": up_event.y,
                    "button": down_event.button or "left"
                }
            )

        # Click or Double-click
        action = ActionType.CLICK
        if down_event.button == "right":
            action = ActionType.RIGHT_CLICK
        else:
            # Check for double click
            if self._last_click:
                lx, ly, lbtn, ltime = self._last_click
                if (lbtn == down_event.button and
                    math.hypot(down_event.x - lx, down_event.y - ly) <= 4 and
                    (down_event.monotonic_ms - ltime) <= self.options.click_debounce_ms):
                    action = ActionType.DOUBLE_CLICK
                    self._last_click = None

        if action != ActionType.DOUBLE_CLICK:
            self._last_click = (down_event.x, down_event.y, down_event.button or "left", down_event.monotonic_ms)

        self._seq += 1
        return self._build_step(
            action=action,
            wall_time_iso=wall_time_iso,
            monotonic_ms=up_event.monotonic_ms,
            ctx=ctx,
            params={
                "x": down_event.x,
                "y": down_event.y,
                "button": down_event.button or "left"
            }
        )

    def _handle_key_down(self, event: RawInputEvent, ctx: Optional[CapturedContext],
                         wall_time_iso: str) -> List[Step]:
        steps: List[Step] = []
        raw_key = event.key_name
        key_upper = raw_key.upper()

        # 1. Check if this is a modifier key (Ctrl, Alt, Shift, Win/Cmd)
        canonical_mod = MODIFIER_MAP.get(key_upper)
        if canonical_mod:
            self._active_modifiers.add(canonical_mod)
            if not self._modifier_context:
                self._modifier_context = ctx
                self._modifier_wall_time = wall_time_iso
                self._modifier_mono_ms = event.monotonic_ms
            # OS sends typematic auto-repeats for modifier keys while held down.
            # Never emit standalone step on key_down for a modifier!
            return steps

        # Track currently held keys to detect OS typematic key-repeats
        is_repeat = raw_key in self._pressed_keys
        self._pressed_keys.add(raw_key)

        # 2. Check if active modifiers form a hotkey combination (e.g. Ctrl+A, Alt+F4, Shift+Tab)
        has_cmd_ctrl_alt = any(m in self._active_modifiers for m in ("CTRL", "ALT", "WIN"))
        is_printable_char = len(raw_key) == 1 and raw_key.isprintable()
        has_shift_combo = ("SHIFT" in self._active_modifiers and not is_printable_char)

        if has_cmd_ctrl_alt or has_shift_combo:
            # Ignore typematic repeats of hotkeys while held down (e.g. holding Ctrl+A)
            if is_repeat:
                return steps

            # Flush any pending regular typing
            flush_step = self._flush_typing(event.monotonic_ms)
            if flush_step:
                steps.append(flush_step)

            # Synthesize combination keys list ordered: CTRL, ALT, SHIFT, WIN, then target key
            order = {"CTRL": 0, "ALT": 1, "SHIFT": 2, "WIN": 3}
            sorted_mods = sorted(self._active_modifiers, key=lambda m: order.get(m, 99))
            key_repr = raw_key.upper() if len(raw_key) == 1 else raw_key
            combo = [*sorted_mods, key_repr]

            self._seq += 1
            key_step = self._build_step(
                action=ActionType.KEY_PRESS,
                wall_time_iso=wall_time_iso or self._modifier_wall_time,
                monotonic_ms=event.monotonic_ms,
                ctx=ctx or self._modifier_context,
                params={"keys": combo}
            )
            if key_step:
                steps.append(key_step)
            self._modifier_used_in_combo = True
            return steps

        # 3. Regular character typing (single printable character with no Ctrl/Alt/Win)
        if is_printable_char:
            # Check typing debounce
            if self._pending_text and (event.monotonic_ms - self._last_key_mono_ms) > self.options.typing_debounce_ms:
                flush_step = self._flush_typing(event.monotonic_ms)
                if flush_step:
                    steps.append(flush_step)

            if not self._pending_text:
                self._pending_type_target = ctx
                self._pending_type_wall_time = wall_time_iso
                self._pending_type_mono_ms = event.monotonic_ms

            self._pending_text.append(raw_key)
            self._last_key_mono_ms = event.monotonic_ms
            return steps

        # 4. Standalone special/navigation key (Enter, Tab, Escape, Backspace, Delete, Arrows, F-keys, etc.)
        if is_repeat and (event.monotonic_ms - self._last_key_mono_ms < 150):
            return steps

        flush_step = self._flush_typing(event.monotonic_ms)
        if flush_step:
            steps.append(flush_step)

        # Emit key_press step
        self._seq += 1
        key_step = self._build_step(
            action=ActionType.KEY_PRESS,
            wall_time_iso=wall_time_iso,
            monotonic_ms=event.monotonic_ms,
            ctx=ctx,
            params={"keys": [raw_key]}
        )
        if key_step:
            steps.append(key_step)
        self._last_key_mono_ms = event.monotonic_ms
        return steps

    def _handle_key_up(self, event: RawInputEvent, ctx: Optional[CapturedContext],
                       wall_time_iso: str) -> List[Step]:
        steps: List[Step] = []
        raw_key = event.key_name
        key_upper = raw_key.upper()

        if raw_key in self._pressed_keys:
            self._pressed_keys.discard(raw_key)

        canonical_mod = MODIFIER_MAP.get(key_upper)
        if canonical_mod:
            self._active_modifiers.discard(canonical_mod)

            # If all modifiers have been released
            if not self._active_modifiers:
                # Standalone tap of Alt (menu bar) or Win (start menu) without any other key
                if not self._modifier_used_in_combo and canonical_mod in ("ALT", "WIN"):
                    press_duration = event.monotonic_ms - (self._modifier_mono_ms or event.monotonic_ms)
                    if press_duration < 600:
                        self._seq += 1
                        key_step = self._build_step(
                            action=ActionType.KEY_PRESS,
                            wall_time_iso=self._modifier_wall_time or wall_time_iso,
                            monotonic_ms=event.monotonic_ms,
                            ctx=self._modifier_context or ctx,
                            params={"keys": [canonical_mod]}
                        )
                        if key_step:
                            steps.append(key_step)

                # Reset modifier tracking state
                self._modifier_used_in_combo = False
                self._modifier_context = None
                self._modifier_wall_time = ""
                self._modifier_mono_ms = 0

        return steps

    def _flush_typing(self, now_ms: int) -> Optional[Step]:
        if not self._pending_text:
            return None

        text = "".join(self._pending_text)
        self._pending_text.clear()
        ctx = self._pending_type_target
        wall_time = self._pending_type_wall_time
        mono_ms = self._pending_type_mono_ms or now_ms

        self._pending_type_target = None
        self._pending_type_wall_time = ""
        self._pending_type_mono_ms = 0

        is_secret = False
        if ctx and ctx.chain and ctx.chain.target and ctx.chain.target.is_password:
            is_secret = True

        if self.options.never_store_text:
            text = ""
            is_secret = True
        elif is_secret and self.options.mask_password_fields:
            text = ""
        elif self.options.redaction_rules:
            for rule in self.options.redaction_rules:
                if rule.scope in ("text", "all") and rule.matches(text):
                    if rule.action == "drop":
                        return None
                    text = rule.redact(text)

        self._seq += 1
        return self._build_step(
            action=ActionType.TYPE,
            wall_time_iso=wall_time,
            monotonic_ms=mono_ms,
            ctx=ctx,
            params={
                "text": text,
                "secret": is_secret
            }
        )

    def _resolve_scroll(self, event: RawInputEvent, ctx: Optional[CapturedContext],
                        wall_time_iso: str) -> Optional[Step]:
        self._seq += 1
        return self._build_step(
            action=ActionType.SCROLL,
            wall_time_iso=wall_time_iso,
            monotonic_ms=event.monotonic_ms,
            ctx=ctx,
            params={"dx": event.dx, "dy": event.dy, "x": event.x, "y": event.y}
        )

    def _build_step(self, action: ActionType, wall_time_iso: str, monotonic_ms: int,
                    ctx: Optional[CapturedContext], params: Dict[str, Any]) -> Optional[Step]:
        import dataclasses
        target_chain = ctx.chain if ctx else None
        resolution = ctx.resolution if ctx else ResolutionMethod.COORDINATES_ONLY
        process = target_chain.process if target_chain else ProcessFacts(pid=0)
        window = target_chain.window if target_chain else WindowFacts(handle=0, title="", class_name="")

        # Apply redaction rules to element names and window titles
        if self.options.redaction_rules:
            for rule in self.options.redaction_rules:
                if rule.scope in ("name", "all"):
                    target_name = target_chain.target.name if (target_chain and target_chain.target) else ""
                    win_title = window.title if window else ""
                    if (target_name and rule.matches(target_name)) or (win_title and rule.matches(win_title)):
                        if rule.action == "drop":
                            return None
                        if target_chain and target_chain.target and target_name and rule.matches(target_name):
                            new_target = dataclasses.replace(target_chain.target, name=rule.redact(target_name))
                            target_chain = dataclasses.replace(target_chain, target=new_target)
                        if window and win_title and rule.matches(win_title):
                            window = dataclasses.replace(window, title=rule.redact(win_title))

        return Step(
            id=str(uuid.uuid4()),
            seq=self._seq,
            action=action,
            created_at=wall_time_iso,
            monotonic_ms=monotonic_ms,
            process=process,
            window=window,
            target=target_chain,
            params=params,
            resolution=resolution
        )
