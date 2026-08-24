"""
Unit tests for SessionManager and Appium REST communication.
"""

import pytest
import responses
from PyQt6.QtCore import QCoreApplication
from xgen.config import XGenConfig
from xgen.core.session_manager import SessionManager, SessionState, WindowInfo

# Ensure QCoreApplication exists for Qt signals
@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@responses.activate
def test_check_server_status_success():
    responses.add(
        responses.GET,
        "http://127.0.0.1:4723/status",
        json={"value": {"ready": True, "message": "The server is ready"}},
        status=200
    )

    is_running, msg = SessionManager.check_server_status("http://127.0.0.1:4723")
    assert is_running is True
    assert "Server running" in msg


@responses.activate
def test_check_server_status_down():
    # No response added -> ConnectionError
    is_running, msg = SessionManager.check_server_status("http://127.0.0.1:9999", timeout_seconds=0.1)
    assert is_running is False
    assert "Connection refused" in msg or "failed" in msg


@responses.activate
def test_create_session_and_fetch_source(qapp):
    mgr = SessionManager()

    # Mock session creation (W3C standard response)
    responses.add(
        responses.POST,
        "http://127.0.0.1:4723/session",
        json={"value": {"sessionId": "test-session-123", "capabilities": {}}},
        status=200
    )

    # Mock window handles
    responses.add(
        responses.GET,
        "http://127.0.0.1:4723/session/test-session-123/window/handles",
        json={"value": ["0x001A0B2C", "0x002B0C3D"]},
        status=200
    )

    # Mock source
    sample_xml = "<AppiumAUT><Window Name='Test Window'><Button Name='OK'/></Window></AppiumAUT>"
    responses.add(
        responses.GET,
        "http://127.0.0.1:4723/session/test-session-123/source",
        json={"value": sample_xml},
        status=200
    )

    # Mock GET /sessions (empty)
    responses.add(
        responses.GET,
        "http://127.0.0.1:4723/sessions",
        json={"value": []},
        status=200
    )

    cfg = XGenConfig(appium_url="http://127.0.0.1:4723", app_path="C:\\test.exe")
    info = mgr._create_session(cfg)

    assert info.session_id == "test-session-123"
    assert len(info.windows) == 2
    assert info.windows[0].handle == "0x001A0B2C"

    # Test source fetch
    src = mgr._fetch_source_internal()
    assert "<AppiumAUT>" in src
    assert "Button" in src

    mgr.close()


@responses.activate
def test_reuse_existing_session_on_server(qapp):
    mgr = SessionManager()

    # Mock GET /sessions returning an active session
    responses.add(
        responses.GET,
        "http://127.0.0.1:4723/sessions",
        json={"value": [{"id": "existing-sess-456", "capabilities": {"appium:app": "Root"}}]},
        status=200
    )

    # Mock window handles for existing session
    responses.add(
        responses.GET,
        "http://127.0.0.1:4723/session/existing-sess-456/window/handles",
        json={"value": ["0x0099AA"]},
        status=200
    )

    cfg = XGenConfig(appium_url="http://127.0.0.1:4723")
    info = mgr._create_session(cfg)

    assert info.session_id == "existing-sess-456"
    assert info.windows[0].handle == "0x0099AA"

    mgr.close()
