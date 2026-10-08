"""
xGen Recorder — Core Data Models and DTOs.
Pure Python dataclasses with to_dict() / from_dict() serialization.
Zero Qt dependencies.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


class ActionType(str, Enum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE = "type"
    KEY_PRESS = "key_press"
    SCROLL = "scroll"
    DRAG_DROP = "drag_drop"
    SWITCH_WINDOW = "switch_window"
    WAIT = "wait"
    ASSERT = "assert"


class ResolutionMethod(str, Enum):
    NATIVE_EXACT = "native_exact"          # Live query on action down
    SCENE_CACHE = "scene_cache"            # Resolved from pre-captured scene snapshot
    COORDINATES_ONLY = "coordinates_only"  # Nothing resolved, coordinate fallback


class LocatorState(str, Enum):
    PENDING = "pending"
    UNIQUE_IN_EVIDENCE = "unique_in_evidence"
    UNVERIFIED = "unverified"
    AMBIGUOUS = "ambiguous"
    APPIUM_VERIFIED = "appium_verified"
    APPIUM_FAILED = "appium_failed"
    UNVERIFIABLE = "unverifiable"
    FAILED = "failed"


class RecorderState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int
    coord_space: str = "win_physical_px"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Bounds:
        return cls(
            left=int(d["left"]),
            top=int(d["top"]),
            right=int(d["right"]),
            bottom=int(d["bottom"]),
            coord_space=str(d.get("coord_space", "win_physical_px"))
        )


@dataclass(frozen=True)
class ElementFacts:
    control_type: str
    name: str = ""
    automation_id: str = ""
    class_name: str = ""
    help_text: str = ""
    runtime_id: str = ""
    bounds: Optional[Bounds] = None
    is_enabled: bool = True
    is_offscreen: bool = False
    is_password: bool = False
    native_handle: int = 0
    extra: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"control_type": self.control_type}
        if self.name:
            d["name"] = self.name
        if self.automation_id:
            d["automation_id"] = self.automation_id
        if self.class_name:
            d["class_name"] = self.class_name
        if self.bounds:
            d["bounds"] = self.bounds.to_dict()
        if self.native_handle:
            d["native_handle"] = self.native_handle
        if self.is_password:
            d["is_password"] = True
        if not self.is_enabled:
            d["is_enabled"] = False
        if self.is_offscreen:
            d["is_offscreen"] = True
        if self.help_text:
            d["help_text"] = self.help_text
        if self.runtime_id:
            d["runtime_id"] = self.runtime_id
        if self.extra:
            d["extra"] = dict(self.extra)
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ElementFacts:
        bounds_data = d.get("bounds")
        bounds = Bounds.from_dict(bounds_data) if bounds_data else None
        return cls(
            control_type=d["control_type"],
            name=d.get("name", ""),
            automation_id=d.get("automation_id", ""),
            class_name=d.get("class_name", ""),
            help_text=d.get("help_text", ""),
            runtime_id=d.get("runtime_id", ""),
            bounds=bounds,
            is_enabled=d.get("is_enabled", True),
            is_offscreen=d.get("is_offscreen", False),
            is_password=d.get("is_password", False),
            native_handle=d.get("native_handle", 0),
            extra=dict(d.get("extra", {}))
        )


@dataclass(frozen=True)
class WindowFacts:
    handle: int
    title: str
    class_name: str
    kind: str = "main"                      # main | dialog | menu | tooltip | popup | unknown
    bounds: Optional[Bounds] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "title": self.title,
            "class_name": self.class_name
        }
        if self.handle:
            d["handle"] = self.handle
        if self.kind and self.kind != "main":
            d["kind"] = self.kind
        if self.bounds:
            d["bounds"] = self.bounds.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> WindowFacts:
        bounds_data = d.get("bounds")
        bounds = Bounds.from_dict(bounds_data) if bounds_data else None
        return cls(
            handle=int(d.get("handle", 0) or 0),
            title=d.get("title", ""),
            class_name=d.get("class_name", ""),
            kind=d.get("kind", "main"),
            bounds=bounds
        )


@dataclass(frozen=True)
class ProcessFacts:
    pid: int
    exe_name: str = ""
    exe_path: str = ""
    bundle_id: str = ""
    app_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"pid": self.pid}
        if self.exe_name:
            d["exe_name"] = self.exe_name
        if self.app_name:
            d["app_name"] = self.app_name
        if self.exe_path:
            d["exe_path"] = self.exe_path
        if self.bundle_id:
            d["bundle_id"] = self.bundle_id
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ProcessFacts:
        return cls(
            pid=int(d.get("pid", 0) or 0),
            exe_name=d.get("exe_name", ""),
            exe_path=d.get("exe_path", ""),
            bundle_id=d.get("bundle_id", ""),
            app_name=d.get("app_name", "")
        )


@dataclass(frozen=True)
class ElementChain:
    target: ElementFacts
    ancestors: Tuple[ElementFacts, ...]      # Nearest first, ending at top window
    window: WindowFacts
    process: ProcessFacts
    complete: bool = True
    true_indices: Optional[Dict[str, int]] = None

    def to_dict(self) -> Dict[str, Any]:
        # Limit stored ancestors to nearest 5 (XPath synthesis scope)
        stored_ancestors = [a.to_dict() for a in self.ancestors[:5]]
        d: Dict[str, Any] = {
            "target": self.target.to_dict(),
            "ancestors": stored_ancestors,
            "complete": self.complete,
        }
        if self.true_indices:
            d["true_indices"] = self.true_indices
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ElementChain:
        win_data = d.get("window")
        window = WindowFacts.from_dict(win_data) if win_data else WindowFacts(handle=0, title="", class_name="")
        proc_data = d.get("process")
        process = ProcessFacts.from_dict(proc_data) if proc_data else ProcessFacts(pid=0)
        return cls(
            target=ElementFacts.from_dict(d["target"]),
            ancestors=tuple(ElementFacts.from_dict(a) for a in d.get("ancestors", [])),
            window=window,
            process=process,
            complete=d.get("complete", True),
            true_indices=d.get("true_indices")
        )


@dataclass(frozen=True)
class CapturedContext:
    chain: ElementChain
    resolution: ResolutionMethod
    captured_at_ms: int
    snapshot_cost_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain": self.chain.to_dict(),
            "resolution": self.resolution.value,
            "captured_at_ms": self.captured_at_ms,
            "snapshot_cost_ms": self.snapshot_cost_ms
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> CapturedContext:
        return cls(
            chain=ElementChain.from_dict(d["chain"]),
            resolution=ResolutionMethod(d["resolution"]),
            captured_at_ms=int(d["captured_at_ms"]),
            snapshot_cost_ms=int(d["snapshot_cost_ms"])
        )


@dataclass
class LocatorCandidate:
    xpath: str
    tier: str
    stability_score: int = 0
    stability_label: str = ""
    state: LocatorState = LocatorState.PENDING
    localization_risk: bool = False
    is_positional: bool = False
    is_data_dependent: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "xpath": self.xpath,
            "tier": self.tier,
            "stability_score": self.stability_score,
            "state": self.state.value
        }
        if self.stability_label:
            d["stability_label"] = self.stability_label
        if self.localization_risk:
            d["localization_risk"] = True
        if self.is_positional:
            d["is_positional"] = True
        if self.is_data_dependent:
            d["is_data_dependent"] = True
        if self.notes:
            d["notes"] = list(self.notes)
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> LocatorCandidate:
        return cls(
            xpath=d["xpath"],
            tier=d.get("tier", "unknown"),
            stability_score=d.get("stability_score", 0),
            stability_label=d.get("stability_label", ""),
            state=LocatorState(d.get("state", LocatorState.PENDING.value)),
            localization_risk=d.get("localization_risk", False),
            is_positional=d.get("is_positional", False),
            is_data_dependent=d.get("is_data_dependent", False),
            notes=list(d.get("notes", []))
        )


@dataclass
class Step:
    id: str
    seq: int
    action: ActionType
    created_at: str                          # ISO 8601 wall time
    monotonic_ms: int
    process: ProcessFacts
    window: WindowFacts
    platform: str = "windows"                # windows | mac
    dialect_key: str = "windows"             # windows | mac2
    target: Optional[ElementChain] = None
    params: Dict[str, Any] = field(default_factory=dict)
    resolution: ResolutionMethod = ResolutionMethod.COORDINATES_ONLY
    locators: List[LocatorCandidate] = field(default_factory=list)
    selected_locator: Optional[int] = None
    locator_state: LocatorState = LocatorState.PENDING
    flags: List[str] = field(default_factory=list)
    notes: str = ""

    def to_action_array(self) -> List[Any]:
        """
        Produce positional JSON array [action, xpath, *args] for automation tools.
        e.g.
          ["click", xpath]
          ["double_click", xpath]
          ["right_click", xpath]
          ["type", xpath, text]
          ["key_press", xpath, key]
          ["scroll", xpath, dx, dy]
        """
        xpath = ""
        if self.locators and self.selected_locator is not None and 0 <= self.selected_locator < len(self.locators):
            xpath = self.locators[self.selected_locator].xpath
        elif self.locators:
            xpath = self.locators[0].xpath

        if self.action in (ActionType.CLICK, ActionType.DOUBLE_CLICK, ActionType.RIGHT_CLICK):
            return [self.action.value, xpath]
        if self.action == ActionType.TYPE:
            text = "[SECRET]" if self.params.get("secret") else self.params.get("text", "")
            return ["type", xpath, text]
        if self.action == ActionType.KEY_PRESS:
            keys = "+".join(self.params.get("keys", []))
            return ["key_press", xpath, keys]
        if self.action == ActionType.SCROLL:
            return ["scroll", xpath, self.params.get("dx", 0), self.params.get("dy", 0)]
        if self.action == ActionType.SWITCH_WINDOW:
            to_win = self.params.get("to_window")
            title = to_win.get("title", "") if isinstance(to_win, dict) else getattr(to_win, "title", "")
            return ["switch_window", xpath, title]
        if self.action == ActionType.WAIT:
            return ["wait", xpath, self.params.get("value", 1)]
        return [self.action.value, xpath]

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "seq": self.seq,
            "action": self.action.value,
            "created_at": self.created_at,
            "window": self.window.to_dict(),
            "process": self.process.to_dict(),
            "id": self.id,
            "monotonic_ms": self.monotonic_ms,
        }
        if self.params:
            d["params"] = dict(self.params)
        if self.target:
            d["target"] = self.target.to_dict()
        if self.locators:
            d["locators"] = [loc.to_dict() for loc in self.locators]
        if self.selected_locator is not None:
            d["selected_locator"] = self.selected_locator
        if self.locator_state != LocatorState.PENDING:
            d["locator_state"] = self.locator_state.value
        if self.flags:
            d["flags"] = list(self.flags)
        if self.notes:
            d["notes"] = self.notes
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Step:
        target_data = d.get("target")
        target = ElementChain.from_dict(target_data) if target_data else None
        proc_data = d.get("process")
        process = ProcessFacts.from_dict(proc_data) if proc_data else ProcessFacts(pid=0)
        win_data = d.get("window")
        window = WindowFacts.from_dict(win_data) if win_data else WindowFacts(handle=0, title="", class_name="")
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            seq=int(d.get("seq", 0)),
            action=ActionType(d["action"]),
            created_at=d.get("created_at", ""),
            monotonic_ms=int(d.get("monotonic_ms", 0)),
            process=process,
            window=window,
            platform=d.get("platform", "windows"),
            dialect_key=d.get("dialect_key", "windows"),
            target=target,
            params=dict(d.get("params", {})),
            resolution=ResolutionMethod(d.get("resolution", ResolutionMethod.COORDINATES_ONLY.value)),
            locators=[LocatorCandidate.from_dict(loc) for loc in d.get("locators", [])],
            selected_locator=d.get("selected_locator"),
            locator_state=LocatorState(d.get("locator_state", LocatorState.PENDING.value)),
            flags=list(d.get("flags", [])),
            notes=d.get("notes", "")
        )


@dataclass
class RecordingMeta:
    id: str
    name: str
    schema_version: int = 1
    tool_version: str = "0.2.0"
    platform: str = "windows"
    dialect_key: str = "windows"
    started_at: str = ""
    stopped_at: Optional[str] = None
    step_count: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "started_at": self.started_at,
            "step_count": self.step_count,
            "duration_seconds": self.duration_seconds
        }
        if self.stopped_at:
            d["stopped_at"] = self.stopped_at
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> RecordingMeta:
        return cls(
            id=d["id"],
            name=d["name"],
            schema_version=d.get("schema_version", 1),
            tool_version=d.get("tool_version", "0.2.0"),
            platform=d.get("platform", "windows"),
            dialect_key=d.get("dialect_key", "windows"),
            started_at=str(d.get("started_at") or ""),
            stopped_at=d.get("stopped_at"),
            step_count=d.get("step_count", 0),
            duration_seconds=float(d.get("duration_seconds", 0.0))
        )


@dataclass
class Recording:
    meta: RecordingMeta
    steps: List[Step] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meta": self.meta.to_dict(),
            "steps": [s.to_dict() for s in self.steps]
        }

    def to_actions_dict(self) -> Dict[str, List[Any]]:
        """
        Returns clean, trimmed positional action-array mapping:
        {
          "1": ["click", "//Button[@Name='Submit']"],
          "2": ["type", "//Edit[@AutomationId='txtUsername']", "admin@test.com"]
        }
        """
        sorted_steps = sorted(self.steps, key=lambda s: s.seq)
        return {
            str(step.seq if step.seq > 0 else i + 1): step.to_action_array()
            for i, step in enumerate(sorted_steps)
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Recording:
        return cls(
            meta=RecordingMeta.from_dict(d["meta"]),
            steps=[Step.from_dict(s) for s in d.get("steps", [])]
        )


@dataclass(frozen=True)
class RawInputEvent:
    kind: str                                # mouse_down | mouse_up | key_down | key_up | scroll
    x: int = 0
    y: int = 0
    button: str = ""                         # left | right | middle
    key_name: str = ""
    dx: int = 0
    dy: int = 0
    monotonic_ms: int = 0


@dataclass(frozen=True)
class SceneEvent:
    kind: str                                # window_open | window_close | menu_open | foreground
    window_handle: int
    title: str = ""
    monotonic_ms: int = 0


@dataclass(frozen=True)
class SimilarFacts:
    count: int
    handles: Tuple[int, ...] = ()


@dataclass(frozen=True)
class SceneSnapshotFacts:
    window: WindowFacts
    elements: Tuple[ElementFacts, ...]
    captured_at_ms: int


@dataclass(frozen=True)
class ContextCapabilities:
    has_native_accessibility: bool = True
    supports_cache_request: bool = True
    supports_fast_popup_hook: bool = True


@dataclass
class RecordingStatus:
    state: RecorderState
    recording_id: Optional[str] = None
    step_count: int = 0
    duration_seconds: float = 0.0
    active_window_title: str = ""
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "recording_id": self.recording_id,
            "step_count": self.step_count,
            "duration_seconds": self.duration_seconds,
            "active_window_title": self.active_window_title,
            "last_error": self.last_error
        }


@dataclass
class PagedSteps:
    steps: List[Step]
    total_count: int
    has_more: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "total_count": self.total_count,
            "has_more": self.has_more
        }


@dataclass
class ExporterInfo:
    id: str
    display_name: str
    file_extension: str
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExportResult:
    text: str
    filename: str
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
