"""
Unit tests for ConfigManager and XGenConfig.
"""

import json
import tempfile
from pathlib import Path
import pytest
from xgen.config import ConfigManager, RecentSession, XGenConfig


def test_default_config_when_file_missing(test_dir: Path):
    missing_file = test_dir / "does_not_exist" / "config.json"
    cfg = ConfigManager.load(missing_file)
    assert cfg.appium_url == "http://127.0.0.1:4723"
    assert cfg.app_path == ""
    assert cfg.recent_sessions == []
    assert cfg.auto_detect_new_windows is True


def test_atomic_save_and_load(test_dir: Path):
    target_file = test_dir / "test_config.json"
    cfg = XGenConfig(
        appium_url="http://192.168.1.100:4723",
        app_path="C:\\Windows\\notepad.exe",
        hover_poll_interval_ms=150,
        recent_sessions=[RecentSession(name="Notepad", app_path="C:\\Windows\\notepad.exe")]
    )

    ConfigManager.save(cfg, target_file)
    assert target_file.exists()

    loaded = ConfigManager.load(target_file)
    assert loaded.appium_url == "http://192.168.1.100:4723"
    assert loaded.app_path == "C:\\Windows\\notepad.exe"
    assert loaded.hover_poll_interval_ms == 150
    assert len(loaded.recent_sessions) == 1
    assert loaded.recent_sessions[0].name == "Notepad"


def test_corrupted_json_fallback(test_dir: Path):
    corrupted_file = test_dir / "bad.json"
    corrupted_file.write_text("{ this is invalid json !!!", encoding="utf-8")

    cfg = ConfigManager.load(corrupted_file)
    assert isinstance(cfg, XGenConfig)
    assert cfg.appium_url == "http://127.0.0.1:4723"


def test_add_recent_session_capping():
    cfg = XGenConfig()
    for i in range(15):
        s = RecentSession(name=f"App_{i}", app_path=f"C:\\app_{i}.exe")
        ConfigManager.add_recent_session(cfg, s)

    assert len(cfg.recent_sessions) == 10
    assert cfg.recent_sessions[0].name == "App_14"  # most recent first
