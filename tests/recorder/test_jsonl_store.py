"""
Tests for JsonlRecordingStore.
Verifies journal appending, fsync durability, atomic finalization,
corrupted line tolerance, and crash recovery.
"""
import json
import pytest
from pathlib import Path

from xgen.recorder.adapters.jsonl_store import JsonlRecordingStore
from xgen.recorder.models import (
    ActionType, LocatorCandidate, LocatorState, ProcessFacts, Recording,
    RecordingMeta, Step, WindowFacts
)


@pytest.fixture
def temp_store(tmp_path):
    return JsonlRecordingStore(root_dir=tmp_path)


def test_jsonl_store_create_append_finalize(temp_store, tmp_path):
    meta = RecordingMeta(id="rec-1", name="TestSession", started_at="2026-10-07T10:00:00Z")
    temp_store.create(meta)

    session_dir = tmp_path / "rec-1"
    assert session_dir.exists()
    assert (session_dir / "meta.json").exists()
    assert (session_dir / "journal.jsonl").exists()

    # Append 2 steps
    win = WindowFacts(handle=10, title="Notepad", class_name="NotepadWnd")
    proc = ProcessFacts(pid=100, exe_name="notepad.exe")

    s1 = Step(
        id="s1", seq=1, action=ActionType.CLICK, created_at="2026-10-07T10:00:01Z",
        monotonic_ms=100, process=proc, window=win,
        locators=[LocatorCandidate(xpath="//Button[@Name='File']", tier="1")]
    )
    s2 = Step(
        id="s2", seq=2, action=ActionType.TYPE, created_at="2026-10-07T10:00:02Z",
        monotonic_ms=200, process=proc, window=win,
        params={"text": "Hello world", "secret": False},
        locators=[LocatorCandidate(xpath="//Edit[@Name='Text']", tier="1")]
    )

    temp_store.append_step("rec-1", s1)
    temp_store.append_step("rec-1", s2)

    # Load before finalize (tests journal replay)
    rec_from_journal = temp_store.load("rec-1")
    assert len(rec_from_journal.steps) == 2
    assert rec_from_journal.steps[0].id == "s1"
    assert rec_from_journal.steps[1].params["text"] == "Hello world"

    # Finalize recording
    rec_final = Recording(meta=meta, steps=[s1, s2])
    temp_store.finalize(rec_final)

    assert (session_dir / "recording.json").exists()
    assert (session_dir / "actions.json").exists()
    assert not (session_dir / "journal.jsonl").exists()
    assert not (session_dir / "meta.json").exists()
    assert len(list(session_dir.iterdir())) == 2

    with open(session_dir / "actions.json", "r", encoding="utf-8") as f:
        actions_data = json.load(f)
    assert actions_data["1"] == ["click", "//Button[@Name='File']"]
    assert actions_data["2"] == ["type", "//Edit[@Name='Text']", "Hello world"]
    rec_loaded = temp_store.load("rec-1")
    assert len(rec_loaded.steps) == 2
    assert rec_loaded.meta.id == "rec-1"


def test_jsonl_store_corrupted_line_tolerance(temp_store, tmp_path):
    meta = RecordingMeta(id="crash-rec", name="Crashed", started_at="2026-10-07T10:00:00Z")
    temp_store.create(meta)

    win = WindowFacts(handle=10, title="App", class_name="Wnd")
    proc = ProcessFacts(pid=100)

    s1 = Step(
        id="s1", seq=1, action=ActionType.CLICK, created_at="2026-10-07T10:00:01Z",
        monotonic_ms=100, process=proc, window=win
    )
    temp_store.append_step("crash-rec", s1)

    # Simulate process killed mid-write leaving half a JSON line
    journal_path = tmp_path / "crash-rec" / "journal.jsonl"
    with open(journal_path, "a", encoding="utf-8") as f:
        f.write('{"id": "corrupted_half_line", "seq": 2, "ac\n')

    # Append valid third step
    s3 = Step(
        id="s3", seq=3, action=ActionType.CLICK, created_at="2026-10-07T10:00:03Z",
        monotonic_ms=300, process=proc, window=win
    )
    temp_store.append_step("crash-rec", s3)

    # Replay journal: should tolerate corrupted line and load s1 and s3
    recovered = temp_store.load("crash-rec")
    assert len(recovered.steps) == 2
    assert recovered.steps[0].id == "s1"
    assert recovered.steps[1].id == "s3"


def test_jsonl_store_incomplete_listing(temp_store, tmp_path):
    meta1 = RecordingMeta(id="rec-done", name="Done", started_at="2026-10-07T10:00:00Z")
    temp_store.create(meta1)
    temp_store.finalize(Recording(meta=meta1, steps=[]))

    meta2 = RecordingMeta(id="rec-unfinalized", name="Incomplete", started_at="2026-10-07T10:05:00Z")
    temp_store.create(meta2)

    incomplete = temp_store.incomplete()
    assert len(incomplete) == 1
    assert incomplete[0].id == "rec-unfinalized"

    # List all
    all_recordings = temp_store.list()
    assert len(all_recordings) == 2


def test_jsonl_store_delete(temp_store, tmp_path):
    meta = RecordingMeta(id="rec-del", name="ToDelete", started_at="2026-10-07T10:00:00Z")
    temp_store.create(meta)
    assert (tmp_path / "rec-del").exists()

    temp_store.delete("rec-del")
    assert not (tmp_path / "rec-del").exists()
