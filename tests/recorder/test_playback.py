"""
Tests for PlaybackRunner.
Verifies JSON-driven automation playback dispatch, action ordering,
progress callbacks, and failure handling using a mock driver.
"""
import json
import pytest
from pathlib import Path

from xgen.recorder.options import PlaybackOptions
from xgen.recorder.playback import PlaybackRunner, load_actions_from_file


class MockElement:
    def __init__(self, xpath: str):
        self.xpath = xpath
        self.clicked = 0
        self.typed_texts = []

    def click(self):
        self.clicked += 1

    def send_keys(self, val):
        self.typed_texts.append(val)


class MockDriver:
    def __init__(self):
        self.elements = {}
        self.window_handles = ["handle1"]
        self.title = "Test App"

    def find_element(self, by, xpath):
        if xpath not in self.elements:
            self.elements[xpath] = MockElement(xpath)
        return self.elements[xpath]


def test_playback_runner_success():
    driver = MockDriver()
    opts = PlaybackOptions(action_delay_seconds=0.0, explicit_wait_seconds=1.0)
    runner = PlaybackRunner(driver, opts)

    actions_map = {
        "1": ["click", "//Button[@Name='OK']"],
        "2": ["type", "//Edit[@Name='User']", "alice"],
        "3": ["key_press", "//Edit[@Name='User']", "ENTER"],
        "4": ["wait", "", 0.01],
    }

    progress = []
    def on_prog(seq, act, ok):
        progress.append((seq, act, ok))

    res = runner.run(actions_map, on_step_progress=on_prog)

    assert res.success is True
    assert res.total_steps == 4
    assert res.executed_steps == 4
    assert len(progress) == 4

    # Verify element operations
    btn = driver.elements["//Button[@Name='OK']"]
    assert btn.clicked == 1

    edit = driver.elements["//Edit[@Name='User']"]
    assert "alice" in edit.typed_texts


def test_playback_runner_failure_handling():
    class FailingDriver:
        def find_element(self, by, xpath):
            if "fail" in xpath:
                raise RuntimeError("Element not found")
            return MockElement(xpath)

    driver = FailingDriver()
    opts = PlaybackOptions(action_delay_seconds=0.0, continue_on_failure=False)
    runner = PlaybackRunner(driver, opts)

    actions = {
        "1": ["click", "//Button[@Name='Good']"],
        "2": ["click", "//Button[@Name='fail']"],
        "3": ["click", "//Button[@Name='AfterFail']"],
    }

    res = runner.run(actions)
    assert res.success is False
    assert res.failed_step == 2
    assert res.executed_steps == 1
    assert "Element not found" in res.error_message


def test_playback_load_actions_from_file(tmp_path):
    fpath = tmp_path / "actions.json"
    actions = {
        "1": ["click", "//Button[@Name='Go']"]
    }
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(actions, f)

    loaded = load_actions_from_file(fpath)
    assert loaded == actions
