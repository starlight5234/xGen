"""
Verification Replay Engine (Phase 10).
Validates recorded candidate XPaths against live Appium sessions or XML source trees
off the recording path, promoting locator states to APPIUM_VERIFIED or APPIUM_FAILED.
Zero Qt dependencies.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

try:
    from appium.webdriver.common.appiumby import AppiumBy
    BY_XPATH = AppiumBy.XPATH
except ImportError:
    BY_XPATH = "xpath"

from xgen.recorder.events import (
    EventBus, VerificationCompletedEvent, VerificationProgressEvent
)
from xgen.recorder.models import (
    LocatorCandidate, LocatorState, Recording, Step
)
from xgen.recorder.ports.store import RecordingStore

logger = logging.getLogger("xgen.recorder.verification")


@dataclass
class StepVerificationResult:
    step_id: str
    seq: int
    tested_xpath: str
    state: LocatorState
    match_count: int = 0
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d


@dataclass
class VerificationReport:
    job_id: str
    recording_id: str
    total_steps: int
    verified_count: int
    failed_count: int
    unverifiable_count: int
    duration_seconds: float
    results: List[StepVerificationResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "recording_id": self.recording_id,
            "total_steps": self.total_steps,
            "verified_count": self.verified_count,
            "failed_count": self.failed_count,
            "unverifiable_count": self.unverifiable_count,
            "duration_seconds": self.duration_seconds,
            "results": [r.to_dict() for r in self.results]
        }


@dataclass
class VerificationJob:
    id: str
    recording_id: str
    status: str = "queued"          # "queued" | "running" | "completed" | "cancelled" | "failed"
    total_steps: int = 0
    completed_steps: int = 0
    report: Optional[VerificationReport] = None
    error: Optional[str] = None
    _cancelled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "recording_id": self.recording_id,
            "status": self.status,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "error": self.error,
            "report": self.report.to_dict() if self.report else None
        }


class VerificationRunner:
    """
    Manages background verification jobs that test recorded locators against an Appium session.
    """
    def __init__(self, event_bus: Optional[EventBus] = None, store: Optional[RecordingStore] = None):
        self.event_bus = event_bus
        self.store = store
        self._jobs: Dict[str, VerificationJob] = {}
        self._lock = threading.RLock()

    def start_job(self, recording: Recording, driver: Any = None,
                  async_run: bool = True) -> str:
        """Starts a verification job for the given recording."""
        job_id = str(uuid.uuid4())
        job = VerificationJob(
            id=job_id,
            recording_id=recording.meta.id,
            status="queued",
            total_steps=len(recording.steps)
        )
        with self._lock:
            self._jobs[job_id] = job

        if async_run:
            worker = threading.Thread(
                target=self._run_job,
                args=(job, recording, driver),
                name=f"xgen-verify-{job_id[:8]}",
                daemon=True
            )
            worker.start()
        else:
            self._run_job(job, recording, driver)

        return job_id

    def get_job(self, job_id: str) -> Optional[VerificationJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in ("queued", "running"):
                job._cancelled = True
                job.status = "cancelled"
                return True
            return False

    def _run_job(self, job: VerificationJob, recording: Recording, driver: Any) -> None:
        job.status = "running"
        t0 = time.monotonic()
        results: List[StepVerificationResult] = []
        verified_cnt = 0
        failed_cnt = 0
        unverifiable_cnt = 0

        logger.info("Starting verification job %s for recording %s (%d steps)",
                    job.id, recording.meta.id, len(recording.steps))

        try:
            for step in recording.steps:
                if job._cancelled:
                    logger.info("Verification job %s cancelled", job.id)
                    job.status = "cancelled"
                    return

                res = self._verify_step(step, driver)
                results.append(res)

                if res.state == LocatorState.APPIUM_VERIFIED:
                    verified_cnt += 1
                elif res.state == LocatorState.APPIUM_FAILED:
                    failed_cnt += 1
                else:
                    unverifiable_cnt += 1

                job.completed_steps += 1
                if self.event_bus:
                    self.event_bus.publish(VerificationProgressEvent(
                        job_id=job.id,
                        recording_id=recording.meta.id,
                        completed_steps=job.completed_steps,
                        total_steps=job.total_steps
                    ))

            elapsed = round(time.monotonic() - t0, 2)
            if job._cancelled:
                job.status = "cancelled"
                return

            report = VerificationReport(
                job_id=job.id,
                recording_id=recording.meta.id,
                total_steps=len(recording.steps),
                verified_count=verified_cnt,
                failed_count=failed_cnt,
                unverifiable_count=unverifiable_cnt,
                duration_seconds=elapsed,
                results=results
            )
            job.report = report
            job.status = "completed"

            # Persist updated recording locator states if store exists
            if self.store:
                try:
                    self.store.finalize(recording)
                except Exception as e:
                    logger.warning("Could not persist updated verification states: %s", e)

            if self.event_bus:
                self.event_bus.publish(VerificationCompletedEvent(
                    job_id=job.id,
                    recording_id=recording.meta.id,
                    passed_count=verified_cnt,
                    failed_count=failed_cnt,
                    unverifiable_count=unverifiable_cnt
                ))

            logger.info("Verification job %s completed in %.2fs: %d verified, %d failed, %d unverifiable",
                        job.id, elapsed, verified_cnt, failed_cnt, unverifiable_cnt)

        except Exception as e:
            logger.exception("Error during verification job %s: %s", job.id, e)
            job.status = "failed"
            job.error = str(e)

    def _verify_step(self, step: Step, driver: Any) -> StepVerificationResult:
        if not step.locators:
            return StepVerificationResult(
                step_id=step.id,
                seq=step.seq,
                tested_xpath="",
                state=LocatorState.UNVERIFIABLE,
                match_count=0,
                reason="Step has no locator candidates"
            )

        idx = step.selected_locator if (step.selected_locator is not None and 0 <= step.selected_locator < len(step.locators)) else 0
        candidate = step.locators[idx]
        xpath = candidate.xpath

        if not driver:
            # No live driver available
            candidate.state = LocatorState.UNVERIFIABLE
            step.locator_state = LocatorState.UNVERIFIABLE
            return StepVerificationResult(
                step_id=step.id,
                seq=step.seq,
                tested_xpath=xpath,
                state=LocatorState.UNVERIFIABLE,
                match_count=0,
                reason="Appium driver unavailable"
            )

        try:
            # Query element in current Appium session
            elements = driver.find_elements(BY_XPATH, xpath)
            count = len(elements)

            if count == 1:
                # Exactly one match -> verified!
                candidate.state = LocatorState.APPIUM_VERIFIED
                step.locator_state = LocatorState.APPIUM_VERIFIED
                return StepVerificationResult(
                    step_id=step.id,
                    seq=step.seq,
                    tested_xpath=xpath,
                    state=LocatorState.APPIUM_VERIFIED,
                    match_count=1,
                    reason="Single unique element matched in Appium session"
                )
            elif count > 1:
                # Ambiguous / duplicate in Appium session
                candidate.state = LocatorState.APPIUM_FAILED
                step.locator_state = LocatorState.APPIUM_FAILED
                return StepVerificationResult(
                    step_id=step.id,
                    seq=step.seq,
                    tested_xpath=xpath,
                    state=LocatorState.APPIUM_FAILED,
                    match_count=count,
                    reason=f"Ambiguous locator: matched {count} elements in Appium session"
                )
            else:
                # Not found
                candidate.state = LocatorState.APPIUM_FAILED
                step.locator_state = LocatorState.APPIUM_FAILED
                return StepVerificationResult(
                    step_id=step.id,
                    seq=step.seq,
                    tested_xpath=xpath,
                    state=LocatorState.APPIUM_FAILED,
                    match_count=0,
                    reason="Element not found in Appium session"
                )

        except Exception as e:
            candidate.state = LocatorState.APPIUM_FAILED
            step.locator_state = LocatorState.APPIUM_FAILED
            return StepVerificationResult(
                step_id=step.id,
                seq=step.seq,
                tested_xpath=xpath,
                state=LocatorState.APPIUM_FAILED,
                match_count=0,
                reason=f"XPath query error: {e}"
            )
