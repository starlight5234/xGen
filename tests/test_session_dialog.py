"""
Unit tests for SessionDialog UI component.
"""

import pytest
from PyQt6.QtWidgets import QApplication
from xgen.config import ConfigManager, RecentSession, XGenConfig
from xgen.core.session_manager import SessionManager
from xgen.ui.session_dialog import SessionDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_session_dialog_initialization(qapp):
    cfg = XGenConfig(appium_url="http://127.0.0.1:4723", app_path="C:\\app.exe")
    mgr = SessionManager()

    dlg = SessionDialog(cfg, mgr)
    assert dlg.app_path_edit.text() == "C:\\app.exe"
    assert dlg.radio_launch.isChecked() is True
    assert dlg.appium_url_edit.text() == "http://127.0.0.1:4723"

    # Switch to Root mode
    dlg.radio_root.setChecked(True)
    dlg._on_mode_changed()
    assert dlg.app_path_edit.isEnabled() is False

    mgr.close()
