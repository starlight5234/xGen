"""
Tests for Recorder CLI transport.
Verifies command line parsing and execution for list, show, and export commands.
"""
import sys
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows CLI recorder tests")

from xgen.recorder.__main__ import main
from xgen.recorder.composition import create_recorder
from xgen.recorder.models import ActionType, LocatorCandidate
from xgen.recorder.options import RecordingOptions


def test_cli_list_and_show(tmp_path, monkeypatch, capsys):
    # Pre-populate a session in tmp_path
    service = create_recorder(storage_dir=tmp_path)
    rec_id = service.start(RecordingOptions(name="CLISession"))
    meta = service.stop()

    # 1. Test `list`
    monkeypatch.setattr("sys.argv", ["xgen.recorder", "list", "--storage-dir", str(tmp_path)])
    rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "CLISession" in captured.out

    # 2. Test `show`
    monkeypatch.setattr("sys.argv", ["xgen.recorder", "show", meta.id, "--storage-dir", str(tmp_path)])
    rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "CLISession" in captured.out


def test_cli_export(tmp_path, monkeypatch, capsys):
    service = create_recorder(storage_dir=tmp_path)
    rec_id = service.start(RecordingOptions(name="ExportCLI"))
    service.stop()

    out_file = tmp_path / "exported.json"
    monkeypatch.setattr("sys.argv", [
        "xgen.recorder", "export", rec_id,
        "--exporter", "action_xpath_json",
        "--output", str(out_file),
        "--storage-dir", str(tmp_path)
    ])
    rc = main()
    assert rc == 0
    assert out_file.exists()
