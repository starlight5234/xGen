"""
Unit tests for TransientCapturer (F4 snapshot, timed capture, freeze mode).
"""

import pytest
from PyQt6.QtWidgets import QApplication
from xgen.capture.transient_capture import TransientCapturer
from xgen.core.tree_cache import TreeCacheStore, WindowTreeCache
from xgen.core.tree_parser import TreeParser, UINode
from xgen.core.uia_bridge import UIAElement
from xgen.utils.rect import Rect


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_frozen_mode_toggle(qapp):
    capturer = TransientCapturer()
    assert capturer.is_frozen is False

    events = []
    capturer.freeze_state_changed.connect(lambda f: events.append(f))

    capturer.set_frozen(True)
    assert capturer.is_frozen is True
    assert events == [True]

    capturer.set_frozen(False)
    assert capturer.is_frozen is False
    assert events == [True, False]


def test_uia_list_to_tree_conversion(qapp):
    capturer = TransientCapturer()

    elements = [
        UIAElement(runtime_id="42.1", control_type="Menu", name="Context"),
        UIAElement(runtime_id="42.2", control_type="MenuItem", name="Copy", automation_id="item_copy"),
        UIAElement(runtime_id="42.3", control_type="MenuItem", name="Paste", automation_id="item_paste"),
    ]

    tree_root = capturer._uia_list_to_tree(elements)
    assert tree_root.tag == "Menu"
    assert tree_root.name == "Context"
    assert tree_root.is_transient is True
    assert len(tree_root.children) == 2
    assert tree_root.children[0].tag == "MenuItem"
    assert tree_root.children[0].automation_id == "item_copy"
    assert tree_root.children[1].automation_id == "item_paste"
