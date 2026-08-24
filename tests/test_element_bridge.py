"""
Unit tests for ElementBridge (UIA Element to XML Node matching).
"""

import pytest
from lxml import etree
from xgen.core.element_bridge import ElementBridge, BridgeResult
from xgen.core.tree_cache import WindowTreeCache
from xgen.core.tree_parser import TreeParser
from xgen.core.uia_bridge import UIAElement
from xgen.utils.rect import Rect

SAMPLE_XML = """
<AppiumAUT>
  <Window Name="App" RuntimeId="42.100" BoundingRectangle="[0,0][1000,800]">
    <Button Name="Submit" AutomationId="btn_submit" RuntimeId="42.101" BoundingRectangle="[100,200][250,230]"/>
    <Button Name="Cancel" AutomationId="btn_cancel" RuntimeId="42.102" BoundingRectangle="[260,200][410,230]"/>
  </Window>
</AppiumAUT>
"""


@pytest.fixture
def sample_cache():
    root = TreeParser.parse(SAMPLE_XML)
    lxml_tree = etree.fromstring(SAMPLE_XML.encode())
    return WindowTreeCache("0x0001", SAMPLE_XML, root, lxml_tree)


def test_bridge_match_by_runtime_id(sample_cache):
    bridge = ElementBridge()
    uia_el = UIAElement(
        runtime_id="42.101",
        control_type="Button",
        name="Submit",
        automation_id="btn_submit"
    )

    res = bridge.find_node(uia_el, sample_cache)
    assert res.node is not None
    assert res.method == "runtime_id"
    assert res.confidence == 1.0
    assert res.node.bridge_confidence == 1.0
    assert res.node.automation_id == "btn_submit"


def test_bridge_match_by_bounding_rect(sample_cache):
    bridge = ElementBridge()
    # Missing RuntimeId, but BoundingRectangle matches
    uia_el = UIAElement(
        runtime_id="",
        control_type="Button",
        name="Cancel",
        bounding_rect=Rect(260, 200, 410, 230)
    )

    res = bridge.find_node(uia_el, sample_cache)
    assert res.node is not None
    assert res.method == "bounding_rect"
    assert 0.8 <= res.confidence <= 1.0
    assert res.node.bridge_confidence == res.confidence
    assert res.node.automation_id == "btn_cancel"


def test_bridge_live_fallback_for_missing_element(sample_cache):
    bridge = ElementBridge()
    # Element does not exist in cached XML snapshot (e.g. virtualized item)
    uia_el = UIAElement(
        runtime_id="42.9999",
        control_type="ListItem",
        name="Row 500",
        automation_id="item_row_500",
        bounding_rect=Rect(100, 500, 300, 530)
    )

    res = bridge.find_node(uia_el, sample_cache)
    assert res.node is not None
    assert res.method == "uia_fallback"
    assert res.confidence == 0.4
    assert res.node.bridge_confidence == 0.4
    assert res.is_live_fallback is True
    assert res.node.tag == "ListItem"
    assert res.node.name == "Row 500"
