"""
JSONL Recording Store Adapter.
Implements the RecordingStore port with crash-resilient append-only journal.jsonl
and consolidated recording.json on finalization.
Zero Qt dependencies.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional

from xgen.recorder.models import Recording, RecordingMeta, Step
from xgen.recorder.ports.store import RecordingStore

logger = logging.getLogger("xgen.recorder.store.jsonl")


class JsonlRecordingStore(RecordingStore):
    """
    Filesystem-backed store managing recording sessions in individual subdirectories.
    Structure:
      <root_dir>/
        <session_id>/
          meta.json
          journal.jsonl
          recording.json
    """
    def __init__(self, root_dir: Optional[Path | str] = None):
        if root_dir is None:
            self.root_dir = Path.home() / ".xgen" / "recordings"
        else:
            self.root_dir = Path(root_dir)
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _session_dir(self, session_id: str) -> Path:
        return self.root_dir / session_id

    def create(self, meta: RecordingMeta) -> None:
        s_dir = self._session_dir(meta.id)
        s_dir.mkdir(parents=True, exist_ok=True)
        meta_file = s_dir / "meta.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta.to_dict(), f, indent=2)

        # Initialize empty journal
        journal_file = s_dir / "journal.jsonl"
        if not journal_file.exists():
            journal_file.touch()

    def append_step(self, recording_id: str, step: Step) -> None:
        s_dir = self._session_dir(recording_id)
        if not s_dir.exists():
            s_dir.mkdir(parents=True, exist_ok=True)
        journal_file = s_dir / "journal.jsonl"
        line = json.dumps(step.to_dict(), ensure_ascii=False)
        with open(journal_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass

    def finalize(self, recording: Recording) -> None:
        s_dir = self._session_dir(recording.meta.id)
        s_dir.mkdir(parents=True, exist_ok=True)

        # 1. Atomic write of clean trimmed actions.json (minimal automation tool format)
        actions_file = s_dir / "actions.json"
        tmp_actions = s_dir / "actions.json.tmp"
        with open(tmp_actions, "w", encoding="utf-8") as f:
            json.dump(recording.to_actions_dict(), f, indent=2, ensure_ascii=False)
        if actions_file.exists():
            actions_file.unlink()
        tmp_actions.replace(actions_file)

        # 2. Atomic write of consolidated recording.json (complete diagnostic document)
        rec_file = s_dir / "recording.json"
        tmp_file = s_dir / "recording.json.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(recording.to_dict(), f, indent=2, ensure_ascii=False)
        
        # Replace atomically
        if rec_file.exists():
            rec_file.unlink()
        tmp_file.replace(rec_file)

        # 3. Clean up streaming write-ahead files (journal.jsonl and meta.json)
        # leaving strictly TWO final output files: actions.json and recording.json
        for temp_name in ("journal.jsonl", "meta.json"):
            temp_path = s_dir / temp_name
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception as e:
                    logger.debug("Failed to remove temporary file %s: %s", temp_path, e)

    def load(self, recording_id: str) -> Recording:
        s_dir = self._session_dir(recording_id)
        if not s_dir.exists():
            raise KeyError(f"Recording session '{recording_id}' does not exist in {self.root_dir}")

        rec_file = s_dir / "recording.json"
        if rec_file.exists():
            with open(rec_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Recording.from_dict(data)

        # Fallback to journal reconstruction
        meta_file = s_dir / "meta.json"
        if not meta_file.exists():
            raise KeyError(f"Missing metadata for session '{recording_id}'")

        with open(meta_file, "r", encoding="utf-8") as f:
            meta_data = json.load(f)
        meta = RecordingMeta.from_dict(meta_data)

        steps: List[Step] = []
        journal_file = s_dir / "journal.jsonl"
        if journal_file.exists():
            with open(journal_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        step_data = json.loads(line)
                        steps.append(Step.from_dict(step_data))
                    except Exception as e:
                        logger.warning("Skipping corrupted journal line: %s", e)

        meta.step_count = len(steps)
        return Recording(meta=meta, steps=steps)

    def list(self) -> List[RecordingMeta]:
        results: List[RecordingMeta] = []
        if not self.root_dir.exists():
            return results

        for child in self.root_dir.iterdir():
            if not child.is_dir():
                continue
            meta_file = child / "meta.json"
            rec_file = child / "recording.json"
            if rec_file.exists():
                try:
                    with open(rec_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    results.append(RecordingMeta.from_dict(data["meta"]))
                    # Clean up temporary streaming files if still lingering in finalized session
                    for temp_name in ("journal.jsonl", "meta.json", "recording.json.tmp", "actions.json.tmp"):
                        tp = child / temp_name
                        if tp.exists():
                            try:
                                tp.unlink()
                            except Exception:
                                pass
                    continue
                except Exception as e:
                    logger.debug("Failed to read %s: %s", rec_file, e)

            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    results.append(RecordingMeta.from_dict(data))
                except Exception as e:
                    logger.debug("Failed to read %s: %s", meta_file, e)

        # Sort newest first
        results.sort(key=lambda m: str(m.started_at or ""), reverse=True)
        return results

    def incomplete(self) -> List[RecordingMeta]:
        """Lists unfinalized sessions having journal.jsonl or meta.json but missing recording.json."""
        results: List[RecordingMeta] = []
        if not self.root_dir.exists():
            return results

        for child in self.root_dir.iterdir():
            if not child.is_dir():
                continue
            rec_file = child / "recording.json"
            if rec_file.exists():
                continue

            meta_file = child / "meta.json"
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    results.append(RecordingMeta.from_dict(data))
                except Exception as e:
                    logger.debug("Failed to read %s: %s", meta_file, e)

        results.sort(key=lambda m: str(m.started_at or ""), reverse=True)
        return results

    def delete(self, recording_id: str) -> None:
        s_dir = self._session_dir(recording_id)
        if s_dir.exists():
            shutil.rmtree(s_dir, ignore_errors=True)
