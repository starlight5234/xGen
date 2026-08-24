"""
Unit tests for TreeParser and UINode model.
"""

import datetime
import pytest
from xgen.core.tree_parser import TreeParser, TreeParseError, UINode
from xgen.utils.rect import Rect

SAMPLE_APPIUM_XML = """
<AppiumAUT>
  <Window Name="Main Window" AutomationId="win_main" ClassName="HwndWrapper"
          BoundingRectangle="[0,0][1920,1080]" RuntimeId="42.1001">
    <Pane Name="Content" ClassName="ScrollViewer" RuntimeId="42.1002">
      <Button Name="Submit" AutomationId="btn_submit" ClassName="WPFButton"
              BoundingRectangle="[100,200][250,230]" RuntimeId="42.1003" IsEnabled="True"/>
      <Button Name="Cancel" AutomationId="btn_cancel" ClassName="WPFButton"
              BoundingRectangle="[260,200][410,230]" RuntimeId="42.1004" IsEnabled="True"/>
      <Edit Name="Username" AutomationId="txt_user" ClassName="TextBox"
            BoundingRectangle="[100,100][300,130]" RuntimeId="42.1005"/>
    </Pane>
  </Window>
</AppiumAUT>
"""

SAMPLE_WAD_XML = """
<Page>
  <Window Name="Outlook" automation-id="win_outlook" class-name="rctrl_renwnd32">
    <Button Name="Send" runtime-id="42.555" bounding-rectangle="[50,50][120,80]"/>
  </Window>
</Page>
"""


def test_parse_appium_xml_structure():
    root = TreeParser.parse(SAMPLE_APPIUM_XML)
    assert root.tag == "AppiumAUT"
    assert len(root.children) == 1

    win = root.children[0]
    assert win.tag == "Window"
    assert win.name == "Main Window"
    assert win.automation_id == "win_main"
    assert win.runtime_id == "42.1001"
    assert win.depth == 1
    assert win.parent == root

    pane = win.children[0]
    assert pane.tag == "Pane"
    assert len(pane.children) == 3

    btn1, btn2, edit = pane.children
    # Sibling index vs Child index (same tag)
    assert btn1.tag == "Button"
    assert btn1.sibling_index == 1
    assert btn1.child_index == 1
    assert btn1.is_enabled is True

    assert btn2.tag == "Button"
    assert btn2.sibling_index == 2
    assert btn2.child_index == 2  # 2nd Button

    assert edit.tag == "Edit"
    assert edit.sibling_index == 3
    assert edit.child_index == 1   # 1st Edit


def test_attribute_normalization():
    root = TreeParser.parse(SAMPLE_WAD_XML)
    win = root.children[0]
    # 'automation-id' -> 'AutomationId', 'class-name' -> 'ClassName'
    assert win.automation_id == "win_outlook"
    assert win.class_name == "rctrl_renwnd32"

    btn = win.children[0]
    assert btn.runtime_id == "42.555"
    assert btn.bounding_rect == Rect(50, 50, 120, 80)


def test_find_by_runtime_id():
    root = TreeParser.parse(SAMPLE_APPIUM_XML)
    node = TreeParser.find_by_runtime_id(root, "42.1003")
    assert node is not None
    assert node.tag == "Button"
    assert node.automation_id == "btn_submit"

    assert TreeParser.find_by_runtime_id(root, "99.9999") is None


def test_find_by_bounding_rect():
    root = TreeParser.parse(SAMPLE_APPIUM_XML)
    rect = Rect(100, 200, 250, 230)
    matches = TreeParser.find_by_bounding_rect(root, rect, "Button")
    assert len(matches) == 1
    assert matches[0].automation_id == "btn_submit"


def test_get_ancestors():
    root = TreeParser.parse(SAMPLE_APPIUM_XML)
    btn = TreeParser.find_by_runtime_id(root, "42.1003")
    assert btn is not None

    ancestors = TreeParser.get_ancestors(btn)
    # Expected ancestor chain from parent up to window (excluding Root)
    assert len(ancestors) == 2
    assert ancestors[0].tag == "Pane"
    assert ancestors[1].tag == "Window"


def test_merge_subtree_and_serialization():
    root = TreeParser.parse(SAMPLE_APPIUM_XML)
    initial_count = TreeParser.node_count(root)

    # Create a transient context menu
    menu = UINode(
        tag="Menu",
        attributes={"Name": "ContextMenu", "AutomationId": "ctx_menu"},
        is_transient=True,
        captured_at=datetime.datetime.now()
    )
    menu_item = UINode(
        tag="MenuItem",
        attributes={"Name": "Copy", "AutomationId": "item_copy"},
        parent=menu,
        is_transient=True
    )
    menu.children.append(menu_item)

    # Merge under root
    TreeParser.merge_subtree(root, menu)
    assert TreeParser.node_count(root) == initial_count + 2

    # Serialize back to XML
    xml_str = TreeParser.to_xml_string(root)
    assert "<Menu" in xml_str
    assert "<MenuItem" in xml_str


def test_expire_transient_nodes():
    root = TreeParser.parse(SAMPLE_APPIUM_XML)

    # Add expired transient node (15 minutes ago)
    old_time = datetime.datetime.now() - datetime.timedelta(minutes=15)
    expired_menu = UINode(
        tag="Menu",
        attributes={"Name": "OldMenu"},
        is_transient=True,
        captured_at=old_time
    )
    TreeParser.merge_subtree(root, expired_menu)

    # Prune with 10 minute TTL
    pruned = TreeParser.expire_transient_nodes(root, ttl_minutes=10)
    assert pruned == 1
    assert TreeParser.find_by_runtime_id(root, "OldMenu") is None
