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


def test_heartbeat_failures_and_flags_initialized(qapp):
    mgr = SessionManager()
    assert hasattr(mgr, "_heartbeat_failures")
    assert mgr._heartbeat_failures == 0
    assert hasattr(mgr, "_disconnect_requested")
    assert mgr._disconnect_requested is False
    assert mgr.http_session is not None
    mgr.close()


@responses.activate
def test_create_session_skips_reuse_for_different_app(qapp):
    mgr = SessionManager()

    # Active session on server is Notepad
    responses.add(
        responses.GET,
        "http://127.0.0.1:4723/sessions",
        json={"value": [{"id": "notepad-sess", "capabilities": {"appium:app": "C:\\Windows\\notepad.exe"}}]},
        status=200
    )

    # Creating a new session for Calculator
    responses.add(
        responses.POST,
        "http://127.0.0.1:4723/session",
        json={"value": {"sessionId": "calc-sess", "capabilities": {}}},
        status=200
    )

    responses.add(
        responses.GET,
        "http://127.0.0.1:4723/session/calc-sess/window/handles",
        json={"value": ["0x00CALC"]},
        status=200
    )

    cfg = XGenConfig(appium_url="http://127.0.0.1:4723", app_path="C:\\Windows\\calc.exe")
    info = mgr._create_session(cfg)

    assert info.session_id == "calc-sess"
    assert info.windows[0].handle == "0x00CALC"

    mgr.close()


def test_element_bridge_refind_escaping():
    from xgen.core.element_bridge import ElementBridge
    from xgen.core.uia_bridge import UIAElement

    bridge = ElementBridge()
    mgr = SessionManager()

    captured_xpaths = []
    mgr.find_element_by_xpath = lambda xp: captured_xpaths.append(xp) or "elem-123"

    # Test element with apostrophe in name
    el = UIAElement(runtime_id="42.100.1", control_type="Button", name="McDonald's App", automation_id="", class_name="Btn")
    bridge._match_by_appium_refind(el, mgr)

    assert len(captured_xpaths) == 1
    # Should use double quotes or concat, not raw single quotes breaking XPath
    assert "McDonald's" in captured_xpaths[0]
    assert captured_xpaths[0] == '//Button[@Name="McDonald\'s App"]'

    mgr.close()


def test_tree_cache_merge_transient_regenerates_node_map():
    from xgen.core.tree_cache import TreeCacheStore, WindowTreeCache
    from xgen.core.tree_parser import TreeParser, UINode
    from lxml import etree

    root = UINode(tag="Window", attributes={"Name": "RootWin"})
    child1 = UINode(tag="Button", attributes={"Name": "Btn1"}, parent=root)
    root.children = [child1]

    node_map = {}
    lxml_elem = TreeParser.to_xml_element(root, node_map)

    cache = WindowTreeCache(
        window_handle="0x001",
        raw_xml="<Window><Button/></Window>",
        parsed_root=root,
        lxml_tree=lxml_elem,
        node_map=node_map
    )

    store = TreeCacheStore.instance()
    store.set("0x001", cache)

    # Merge transient node
    transient = UINode(tag="MenuItem", attributes={"Name": "TransientItem"})
    store.merge_transient("0x001", transient)

    updated_cache = store.get("0x001")
    assert updated_cache is not None
    assert len(updated_cache.node_map) >= 3  # Window, Button, MenuItem
    assert any(n.attributes.get("Name") == "TransientItem" for n in updated_cache.node_map.values())

