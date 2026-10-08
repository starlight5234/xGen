"""
Tests for Recorder Data Models and Action Serialization.
"""
import pytest
from xgen.recorder.models import (
    ActionType, Bounds, ElementFacts, LocatorCandidate, LocatorState,
    ProcessFacts, Step, WindowFacts
)


def test_step_to_action_array_positional_contract():
    """
    Verifies that Step.to_action_array() formats actions into clean positional lists:
      ["click", xpath]
      ["double_click", xpath]
      ["right_click", xpath]
      ["type", xpath, text]
      ["key_press", xpath, key]
      ["scroll", xpath, dx, dy]
    """
    win = WindowFacts(handle=1, title="App", class_name="Wnd")
    proc = ProcessFacts(pid=100)

    # 1. Click
    step_click = Step(
        id="s1", seq=1, action=ActionType.CLICK, created_at="2026-10-07T12:00:00Z", monotonic_ms=100,
        process=proc, window=win,
        locators=[LocatorCandidate(xpath="//Button[@Name='Submit']", tier="1")]
    )
    assert step_click.to_action_array() == ["click", "//Button[@Name='Submit']"]

    # 2. Type with text
    step_type = Step(
        id="s2", seq=2, action=ActionType.TYPE, created_at="2026-10-07T12:00:01Z", monotonic_ms=200,
        process=proc, window=win,
        params={"text": "admin@test.com", "secret": False},
        locators=[LocatorCandidate(xpath="//Edit[@AutomationId='txtUser']", tier="1")]
    )
    assert step_type.to_action_array() == ["type", "//Edit[@AutomationId='txtUser']", "admin@test.com"]

    # 3. Type with secret password
    step_pw = Step(
        id="s3", seq=3, action=ActionType.TYPE, created_at="2026-10-07T12:00:02Z", monotonic_ms=300,
        process=proc, window=win,
        params={"text": "mypassword", "secret": True},
        locators=[LocatorCandidate(xpath="//Edit[@AutomationId='txtPass']", tier="1")]
    )
    assert step_pw.to_action_array() == ["type", "//Edit[@AutomationId='txtPass']", "[SECRET]"]

    # 4. Key Press
    step_key = Step(
        id="s4", seq=4, action=ActionType.KEY_PRESS, created_at="2026-10-07T12:00:03Z", monotonic_ms=400,
        process=proc, window=win,
        params={"keys": ["ENTER"]},
        locators=[LocatorCandidate(xpath="//Edit[@AutomationId='txtUser']", tier="1")]
    )
    assert step_key.to_action_array() == ["key_press", "//Edit[@AutomationId='txtUser']", "ENTER"]

    # 5. Scroll
    step_scroll = Step(
        id="s5", seq=5, action=ActionType.SCROLL, created_at="2026-10-07T12:00:04Z", monotonic_ms=500,
        process=proc, window=win,
        params={"dx": 0, "dy": -120},
        locators=[LocatorCandidate(xpath="//Pane[@Name='List']", tier="1")]
    )
    assert step_scroll.to_action_array() == ["scroll", "//Pane[@Name='List']", 0, -120]


def test_step_roundtrip_serialization():
    """Verifies lossless roundtrip to_dict() and from_dict()."""
    win = WindowFacts(handle=1, title="Test Window", class_name="WndClass", bounds=Bounds(0, 0, 800, 600))
    proc = ProcessFacts(pid=500, exe_name="app.exe")
    step = Step(
        id="step-123", seq=1, action=ActionType.CLICK, created_at="2026-10-07T12:00:00Z", monotonic_ms=1000,
        process=proc, window=win,
        params={"button": "left", "x": 150, "y": 250},
        locators=[
            LocatorCandidate(xpath="//Button[@Name='OK']", tier="1", stability_score=85, state=LocatorState.UNIQUE_IN_EVIDENCE)
        ],
        selected_locator=0,
        notes="Verified in evidence"
    )

    data = step.to_dict()
    restored = Step.from_dict(data)

    assert restored.id == step.id
    assert restored.seq == step.seq
    assert restored.action == step.action
    assert restored.window.title == "Test Window"
    assert restored.process.exe_name == "app.exe"
    assert len(restored.locators) == 1
    assert restored.locators[0].xpath == "//Button[@Name='OK']"
    assert restored.locators[0].state == LocatorState.UNIQUE_IN_EVIDENCE
    assert restored.to_action_array() == ["click", "//Button[@Name='OK']"]
