"""
Verification Replay Tests (Phase 10).
Validates locator promotion to APPIUM_VERIFIED / APPIUM_FAILED,
progress and completed events, cancellation, and API service integration.
"""
import time
from typing import List, Optional
import pytest

from xgen.recorder.adapters.jsonl_store import JsonlRecordingStore
from xgen.recorder.events import (
    EventBus, VerificationCompletedEvent, VerificationProgressEvent
)
from xgen.recorder.models import (
    ActionType, Bounds, CapturedContext, ElementChain, ElementFacts,
    LocatorCandidate, LocatorState, ProcessFacts, RawInputEvent,
    Recording, RecordingMeta, ResolutionMethod, Step, WindowFacts
)
from xgen.recorder.ports.clock import Clock
from xgen.recorder.ports.context import NativeContextProvider
from xgen.recorder.ports.input_source import InputSource
from xgen.recorder.service import RecorderService
from xgen.recorder.verification import VerificationRunner


class FakeClock(Clock):
    def monotonic_ms(self) -> int:
        return 1000

    def wall_time_iso(self) -> str:
        return "2026-10-08T00:00:00Z"


class FakeInputSource(InputSource):
    def start(self, sink) -> None: pass
    def stop(self) -> None: pass
    def is_running(self) -> bool: return False


class FakeContextProvider(NativeContextProvider):
    def cursor_position(self): return (0, 0)
    def capture_at(self, x, y, *, deadline_ms=150): return None
    def capture_focused(self, *, deadline_ms=150): return None
    def find_similar(self, ctx, *, limit=10, deadline_ms=80):
        from xgen.recorder.models import SimilarFacts
        return SimilarFacts(count=1, handles=(1001,))


class MockAppiumDriver:
    """Simulates an Appium WebDriver session for XPath evaluation."""
    def __init__(self, elements_by_xpath: Optional[dict] = None):
        self.elements_by_xpath = elements_by_xpath or {}

    def find_elements(self, by, xpath):
        return self.elements_by_xpath.get(xpath, [])


def create_sample_recording(xpath: str = "//Button[@Name='OK']") -> Recording:
    meta = RecordingMeta(id="verify-sess-1", name="Verification Session", started_at="2026-10-08T00:00:00Z")
    cand = LocatorCandidate(
        xpath=xpath,
        tier="unique_attribute",
        stability_score=90,
        state=LocatorState.UNIQUE_IN_EVIDENCE
    )
    step = Step(
        id="step-1",
        seq=1,
        action=ActionType.CLICK,
        created_at="2026-10-08T00:00:01Z",
        monotonic_ms=1050,
        process=ProcessFacts(pid=100, exe_name="app.exe"),
        window=WindowFacts(handle=1001, title="Test", class_name="Wnd"),
        params={"button": "left"},
        locators=[cand],
        selected_locator=0
    )
    return Recording(meta=meta, steps=[step])


def test_verification_promotes_unique_locator_to_verified(tmp_path):
    """Verify single element match in Appium session promotes candidate to APPIUM_VERIFIED."""
    bus = EventBus()
    completed_events = []
    bus.subscribe(VerificationCompletedEvent, lambda e: completed_events.append(e))

    runner = VerificationRunner(event_bus=bus)
    recording = create_sample_recording("//Button[@Name='OK']")

    mock_driver = MockAppiumDriver(elements_by_xpath={
        "//Button[@Name='OK']": ["<Element1>"]
    })

    job_id = runner.start_job(recording, driver=mock_driver, async_run=False)
    job = runner.get_job(job_id)

    assert job is not None
    assert job.status == "completed"
    assert job.report.verified_count == 1
    assert job.report.failed_count == 0
    assert recording.steps[0].locators[0].state == LocatorState.APPIUM_VERIFIED
    assert len(completed_events) == 1
    assert completed_events[0].passed_count == 1


def test_verification_flags_ambiguous_locator_as_failed():
    """Verify multiple matches in Appium session sets candidate to APPIUM_FAILED."""
    runner = VerificationRunner()
    recording = create_sample_recording("//Button[@Name='Ambiguous']")

    mock_driver = MockAppiumDriver(elements_by_xpath={
        "//Button[@Name='Ambiguous']": ["<Element1>", "<Element2>"]
    })

    job_id = runner.start_job(recording, driver=mock_driver, async_run=False)
    job = runner.get_job(job_id)

    assert job.status == "completed"
    assert job.report.verified_count == 0
    assert job.report.failed_count == 1
    assert recording.steps[0].locators[0].state == LocatorState.APPIUM_FAILED
    assert "Ambiguous locator: matched 2 elements" in job.report.results[0].reason


def test_verification_flags_missing_locator_as_failed():
    """Verify missing element in Appium session sets candidate to APPIUM_FAILED."""
    runner = VerificationRunner()
    recording = create_sample_recording("//Button[@Name='NonExistent']")

    mock_driver = MockAppiumDriver(elements_by_xpath={})

    job_id = runner.start_job(recording, driver=mock_driver, async_run=False)
    job = runner.get_job(job_id)

    assert job.status == "completed"
    assert job.report.failed_count == 1
    assert recording.steps[0].locators[0].state == LocatorState.APPIUM_FAILED
    assert "Element not found" in job.report.results[0].reason


def test_verification_handles_unavailable_driver():
    """Verify missing driver marks steps as UNVERIFIABLE without throwing an error."""
    runner = VerificationRunner()
    recording = create_sample_recording("//Button[@Name='OK']")

    job_id = runner.start_job(recording, driver=None, async_run=False)
    job = runner.get_job(job_id)

    assert job.status == "completed"
    assert job.report.unverifiable_count == 1
    assert recording.steps[0].locators[0].state == LocatorState.UNVERIFIABLE


def test_verification_job_cancellation():
    """Verify cancellation of an active verification job."""
    runner = VerificationRunner()
    meta = RecordingMeta(id="sess-cancel", name="Cancel Session")
    steps = [
        Step(
            id=f"step-{i}",
            seq=i,
            action=ActionType.CLICK,
            created_at="",
            monotonic_ms=1000 + i,
            process=ProcessFacts(pid=1),
            window=WindowFacts(handle=1, title="", class_name=""),
            locators=[LocatorCandidate(xpath=f"//Item[{i}]", tier="tag", stability_score=50)]
        )
        for i in range(100)
    ]
    recording = Recording(meta=meta, steps=steps)

    # Delay find_elements to give time for cancellation
    class SlowDriver:
        def find_elements(self, by, xpath):
            time.sleep(0.05)
            return ["<El>"]

    job_id = runner.start_job(recording, driver=SlowDriver(), async_run=True)
    time.sleep(0.02)
    cancelled = runner.cancel_job(job_id)
    assert cancelled is True
    job = runner.get_job(job_id)
    assert job.status == "cancelled"


def test_verification_service_api_integration(tmp_path):
    """Verify full end-to-end flow through RecorderService APIs."""
    store = JsonlRecordingStore(root_dir=tmp_path)
    service = RecorderService(
        clock=FakeClock(),
        input_source=FakeInputSource(),
        context_provider=FakeContextProvider(),
        store=store
    )

    # Pre-save a recording
    recording = create_sample_recording("//Edit[@AutomationId='txt1']")
    store.create(recording.meta)
    store.finalize(recording)

    mock_driver = MockAppiumDriver(elements_by_xpath={
        "//Edit[@AutomationId='txt1']": ["<EditEl>"]
    })

    # Start verification via RecorderApi
    job_id = service.start_verification(recording.meta.id, driver=mock_driver)
    time.sleep(0.05)

    job = service.get_verification_job(job_id)
    assert job is not None
    assert job.status == "completed"
    assert job.report.verified_count == 1
