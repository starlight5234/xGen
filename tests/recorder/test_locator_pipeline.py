"""
Tests for EvidenceBuilder, LocatorEngine, and the locator pipeline.
Verifies synthesis of ranked Appium XPaths from native context and uniqueness classification.
Zero Qt dependencies.
"""
import pytest
from xgen.core.driver_dialect import active_dialect
from xgen.recorder.locators.engine import LocatorEngine
from xgen.recorder.locators.evidence_builder import EvidenceBuilder
from xgen.recorder.models import (
    Bounds, CapturedContext, ElementChain, ElementFacts, LocatorState,
    ProcessFacts, ResolutionMethod, SimilarFacts, WindowFacts
)


@pytest.fixture
def sample_context():
    target = ElementFacts(
        control_type="Button",
        name="Submit",
        automation_id="btnSubmit",
        class_name="ButtonClass",
        bounds=Bounds(100, 100, 200, 150)
    )
    parent = ElementFacts(
        control_type="Pane",
        name="MainPanel",
        automation_id="panelMain",
        class_name="PaneClass"
    )
    win_fact = ElementFacts(
        control_type="Window",
        name="MyApplication",
        automation_id="winApp",
        class_name="WindowClass"
    )
    chain = ElementChain(
        target=target,
        ancestors=(parent, win_fact),
        window=WindowFacts(handle=0x1234, title="MyApplication", class_name="WindowClass"),
        process=ProcessFacts(pid=5678, exe_name="app.exe")
    )
    return CapturedContext(
        chain=chain,
        resolution=ResolutionMethod.NATIVE_EXACT,
        captured_at_ms=1000,
        snapshot_cost_ms=2
    )


def test_evidence_builder_tree_structure(sample_context):
    builder = EvidenceBuilder(dialect=active_dialect())
    root, target = builder.build_tree(sample_context)

    # Root should be window
    assert root.tag == "Window"
    assert root.attributes["Name"] == "MyApplication"

    # Hierarchy should lead to target
    assert target.tag == "Button"
    assert target.attributes["Name"] == "Submit"
    assert target.parent is not None
    assert target.parent.tag == "Pane"
    assert target.parent.attributes["Name"] == "MainPanel"
    assert target.parent.parent is root


def test_locator_engine_synthesizes_unique_candidates(sample_context):
    engine = LocatorEngine(dialect=active_dialect())
    candidates = engine.generate_locators(sample_context)

    assert len(candidates) > 0

    # Top candidate should be ranked high
    top = candidates[0]
    assert "//Button" in top.xpath or "//*[@Name='Submit']" in top.xpath
    assert top.stability_score >= 50
    assert top.state == LocatorState.UNIQUE_IN_EVIDENCE


def test_locator_engine_handles_duplicates():
    # Create target with duplicate sibling
    target = ElementFacts(control_type="Button", name="DuplicateBtn", automation_id="btnDup1")
    parent = ElementFacts(control_type="Group", name="LeftGroup", automation_id="grpLeft")
    win_fact = ElementFacts(control_type="Window", name="TestWin", automation_id="winMain")

    chain = ElementChain(
        target=target,
        ancestors=(parent, win_fact),
        window=WindowFacts(handle=1, title="TestWin", class_name="Wnd"),
        process=ProcessFacts(pid=100)
    )
    ctx = CapturedContext(chain=chain, resolution=ResolutionMethod.NATIVE_EXACT, captured_at_ms=1000, snapshot_cost_ms=1)

    # Report 2 similar elements
    similar = SimilarFacts(count=2, handles=(10, 20))

    engine = LocatorEngine(dialect=active_dialect())
    candidates = engine.generate_locators(ctx, similar)

    # Any naked //Button[@Name='DuplicateBtn'] without container should match both duplicate nodes and be AMBIGUOUS
    ambiguous = [c for c in candidates if c.state == LocatorState.AMBIGUOUS]
    assert len(ambiguous) >= 1
    assert ambiguous[0].xpath == "//Button[@Name='DuplicateBtn']" or ambiguous[0].xpath == "//*[@Name='DuplicateBtn']"

    # Container-anchored candidates (with LeftGroup) should remain UNIQUE_IN_EVIDENCE
    unique = [c for c in candidates if c.state == LocatorState.UNIQUE_IN_EVIDENCE]
    assert len(unique) >= 1
    assert any("LeftGroup" in c.xpath or "grpLeft" in c.xpath for c in unique)


def test_locator_engine_popup_empty_window_title_and_sanitized_tag():
    """Verify popup/transient window with empty title and multi-word control type synthesizes valid XPaths."""
    target = ElementFacts(
        control_type="Menu Item",
        name="Save As...",
        automation_id="",
        class_name="MenuItemClass",
        bounds=Bounds(10, 20, 100, 50)
    )
    chain = ElementChain(
        target=target,
        ancestors=(),
        window=WindowFacts(handle=0x5678, title="", class_name="Popup", kind="popup"),
        process=ProcessFacts(pid=100)
    )
    ctx = CapturedContext(
        chain=chain,
        resolution=ResolutionMethod.NATIVE_EXACT,
        captured_at_ms=100,
        snapshot_cost_ms=1
    )

    engine = LocatorEngine(dialect=active_dialect())
    candidates = engine.generate_locators(ctx)

    assert len(candidates) > 0
    # Tag must be sanitized to valid XML (no space like "Menu Item")
    for c in candidates:
        assert "Menu Item" not in c.xpath, f"XPath must not contain space in tag: {c.xpath}"
    assert any("//MenuItem" in c.xpath for c in candidates)
    assert any("Save As..." in c.xpath for c in candidates)


def test_service_build_fallback_locator():
    """Verify fallback locator generator guarantees valid, non-empty XPath for steps lacking target."""
    from xgen.recorder.service import RecorderService
    from xgen.recorder.models import ActionType, Step

    # 1. Step with window title
    step1 = Step(
        id="s1",
        seq=1,
        action=ActionType.CLICK,
        created_at="2026-10-08T12:00:00Z",
        monotonic_ms=1000,
        process=ProcessFacts(pid=10),
        window=WindowFacts(handle=1, title="Popup Window", class_name="Popup", kind="popup"),
        params={"x": 50, "y": 60}
    )
    # Fake service instance for helper testing
    srv = RecorderService.__new__(RecorderService)
    loc1 = srv._build_fallback_locator(step1)
    assert loc1 is not None
    assert "//Window[@Name='Popup Window']" == loc1.xpath

    # 2. Step with only popup class name and empty title
    step2 = Step(
        id="s2",
        seq=2,
        action=ActionType.CLICK,
        created_at="2026-10-08T12:00:00Z",
        monotonic_ms=1000,
        process=ProcessFacts(pid=10),
        window=WindowFacts(handle=2, title="", class_name="ComboLBox", kind="popup"),
        params={"x": 50, "y": 60}
    )
    loc2 = srv._build_fallback_locator(step2)
    assert loc2 is not None
    assert "//Window[@ClassName='ComboLBox']" == loc2.xpath
    step2.locators = [loc2]
    step2.selected_locator = 0
    # Ensure to_action_array produces non-empty locator
    arr = step2.to_action_array()
    assert arr[0] == "click"
    assert arr[1] == "//Window[@ClassName='ComboLBox']"
