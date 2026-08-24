import responses
from PyQt6.QtWidgets import QApplication
from xgen.config import XGenConfig
from xgen.core.session_manager import SessionManager, SessionState
from xgen.core.driver_runner import DriverRunner

def test_driver_runner_no_session(qapp):
    sm = SessionManager()
    runner = DriverRunner(sm)
    res = runner.test_xpath("//Button[@Name='Test']")
    assert res.success is False
    assert "No active Appium session" in res.error_message
    sm.close()

@responses.activate
def test_driver_runner_test_and_click(qapp):
    sm = SessionManager()
    sm._session_id = "test-session-123"
    sm._base_url = "http://127.0.0.1:4723"
    sm.state = SessionState.CONNECTED

    # Mock POST /element (1st for test_xpath, 2nd for click_xpath)
    for _ in range(2):
        responses.add(
            responses.POST,
            "http://127.0.0.1:4723/session/test-session-123/element",
            json={"value": {"ELEMENT": "elem-456"}},
            status=200
        )
        responses.add(
            responses.GET,
            "http://127.0.0.1:4723/session/test-session-123/element/elem-456/rect",
            json={"value": {"x": 50, "y": 100, "width": 80, "height": 30}},
            status=200
        )

    # Mock POST /element/elem-456/click
    responses.add(
        responses.POST,
        "http://127.0.0.1:4723/session/test-session-123/element/elem-456/click",
        json={"value": None},
        status=200
    )

    runner = DriverRunner(sm)
    res = runner.test_xpath("//Button[@Name='Submit']")
    assert res.success is True
    assert res.element_id == "elem-456"
    assert res.bounding_rect is not None
    assert res.bounding_rect.left == 50
    assert res.bounding_rect.top == 100

    clicked = runner.click_xpath("//Button[@Name='Submit']")
    assert clicked is True

    # Mock POST /element (for send_keys)
    responses.add(
        responses.POST,
        "http://127.0.0.1:4723/session/test-session-123/element",
        json={"value": {"ELEMENT": "elem-456"}},
        status=200
    )
    responses.add(
        responses.GET,
        "http://127.0.0.1:4723/session/test-session-123/element/elem-456/rect",
        json={"value": {"x": 50, "y": 100, "width": 80, "height": 30}},
        status=200
    )
    responses.add(
        responses.POST,
        "http://127.0.0.1:4723/session/test-session-123/element/elem-456/value",
        json={"value": None},
        status=200
    )
    typed = runner.send_keys_xpath("//Edit[@Name='Input']", "test")
    assert typed is True

    # Mock POST /element and /actions (for hover)
    responses.add(
        responses.POST,
        "http://127.0.0.1:4723/session/test-session-123/element",
        json={"value": {"ELEMENT": "elem-456"}},
        status=200
    )
    responses.add(
        responses.GET,
        "http://127.0.0.1:4723/session/test-session-123/element/elem-456/rect",
        json={"value": {"x": 50, "y": 100, "width": 80, "height": 30}},
        status=200
    )
    responses.add(
        responses.POST,
        "http://127.0.0.1:4723/session/test-session-123/actions",
        json={"value": None},
        status=200
    )
    hovered = runner.hover_xpath("//Button[@Name='Submit']")
    assert hovered is True

    sm.close()
