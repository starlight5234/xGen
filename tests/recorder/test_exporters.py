"""
Tests for Exporters and Exporter Registry.
Verifies action_xpath_json, raw_json, pytest_appium, and registry behaviors.
"""
import json
import pytest

from xgen.recorder.exporters.action_xpath_json import ActionXpathJsonExporter
from xgen.recorder.exporters.pytest_appium import PytestAppiumExporter
from xgen.recorder.exporters.raw_json import RawJsonExporter
from xgen.recorder.exporters.registry import (
    ExporterRegistry, default_registry, get_exporter, list_exporters
)
from xgen.recorder.models import (
    ActionType, LocatorCandidate, LocatorState, ProcessFacts, Recording,
    RecordingMeta, Step, WindowFacts
)


@pytest.fixture
def sample_recording():
    meta = RecordingMeta(id="test-exp-1", name="Checkout Flow", started_at="2026-10-07T14:00:00Z")
    win = WindowFacts(handle=10, title="Shopping App", class_name="ShopWnd")
    proc = ProcessFacts(pid=500, exe_name="app.exe", exe_path="C:\\Program Files\\App\\app.exe")

    s1 = Step(
        id="s1", seq=1, action=ActionType.CLICK, created_at="2026-10-07T14:00:01Z",
        monotonic_ms=1000, process=proc, window=win,
        locators=[LocatorCandidate(xpath="//Button[@Name='Checkout']", tier="1", state=LocatorState.UNIQUE_IN_EVIDENCE)]
    )
    s2 = Step(
        id="s2", seq=2, action=ActionType.TYPE, created_at="2026-10-07T14:00:02Z",
        monotonic_ms=2000, process=proc, window=win,
        params={"text": "secret123", "secret": True},
        locators=[LocatorCandidate(xpath="//Edit[@AutomationId='txtPass']", tier="1", state=LocatorState.UNIQUE_IN_EVIDENCE)]
    )
    s3 = Step(
        id="s3", seq=3, action=ActionType.KEY_PRESS, created_at="2026-10-07T14:00:03Z",
        monotonic_ms=3000, process=proc, window=win,
        params={"keys": ["ENTER"]},
        locators=[LocatorCandidate(xpath="//Edit[@AutomationId='txtPass']", tier="1", state=LocatorState.UNIQUE_IN_EVIDENCE)]
    )
    s4 = Step(
        id="s4", seq=4, action=ActionType.CLICK, created_at="2026-10-07T14:00:04Z",
        monotonic_ms=4000, process=proc, window=win,
        locators=[LocatorCandidate(xpath="//Button[@Name='Unverified']", tier="1", state=LocatorState.AMBIGUOUS)]
    )
    s5 = Step(
        id="s5", seq=5, action=ActionType.CLICK, created_at="2026-10-07T14:00:05Z",
        monotonic_ms=5000, process=proc, window=win,
        params={"x": 50, "y": 75},
        locators=[]  # Unresolved
    )

    return Recording(meta=meta, steps=[s1, s2, s3, s4, s5])


def test_action_xpath_json_exporter(sample_recording):
    exp = ActionXpathJsonExporter()
    res = exp.export(sample_recording, {"indent": 2, "include_unverified": True})

    assert res.filename == "Checkout_Flow.json"
    data = json.loads(res.text)

    # 1. Click
    assert data["1"] == ["click", "//Button[@Name='Checkout']"]
    # 2. Secret type
    assert data["2"] == ["type", "//Edit[@AutomationId='txtPass']", "[SECRET]"]
    # 3. Key press
    assert data["3"] == ["key_press", "//Edit[@AutomationId='txtPass']", "ENTER"]
    # 4. Ambiguous locator included when include_unverified=True
    assert data["4"] == ["click", "//Button[@Name='Unverified']"]
    # 5. Unresolved element has empty xpath
    assert data["5"] == ["click", ""]

    # Verify warning for step 5
    assert any("Unresolved element" in w for w in res.warnings)


def test_action_xpath_json_suppresses_unverified(sample_recording):
    exp = ActionXpathJsonExporter()
    res = exp.export(sample_recording, {"indent": 2, "include_unverified": False})

    data = json.loads(res.text)
    # Step 4 locator suppressed
    assert data["4"] == ["click", ""]
    assert any("Suppressed unverified locator" in w for w in res.warnings)


def test_raw_json_exporter(sample_recording):
    exp = RawJsonExporter()
    res = exp.export(sample_recording, {"indent": 2})

    assert res.filename == "Checkout_Flow_raw.json"
    data = json.loads(res.text)
    assert data["meta"]["name"] == "Checkout Flow"
    assert len(data["steps"]) == 5


def test_pytest_appium_exporter(sample_recording):
    exp = PytestAppiumExporter()
    res = exp.export(sample_recording, {
        "session_scope": "app_launch",
        "appium_url": "http://localhost:4723",
        "explicit_wait_seconds": 5.0,
        "include_unverified": True,
        "parameterize_secrets": True
    })

    assert res.filename == "test_checkout_flow.py"
    code = res.text

    assert "import pytest" in code
    assert "from appium import webdriver" in code
    assert 'EXPLICIT_WAIT = 5.0' in code
    assert 'options.set_capability("app", "C:\\\\Program Files\\\\App\\\\app.exe")' in code
    assert '_find(driver, "//Button[@Name=\'Checkout\']").click()' in code
    assert 'os.environ.get("SECRET_1"' in code
    assert 'actions.send_keys(Keys.ENTER).perform()' in code


def test_exporter_registry():
    reg = default_registry()
    assert reg.get("action_xpath_json") is not None
    assert reg.get("raw_json") is not None
    assert reg.get("pytest_appium") is not None
    assert len(reg.list()) >= 3
    assert get_exporter("action_xpath_json") is not None
    assert len(list_exporters()) >= 3
