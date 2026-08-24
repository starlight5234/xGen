"""
Unit tests for UI Panels (Toolbar, TreePanel, AttributePanel, XPathPanel, MainWindow).
"""

import pytest
from lxml import etree
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from xgen.config import XGenConfig
from xgen.core.tree_parser import TreeParser, UINode
from xgen.ui.attribute_panel import AttributePanel
from xgen.ui.main_window import MainWindow
from xgen.ui.toolbar import Toolbar
from xgen.ui.tree_panel import TreePanel
from xgen.ui.xpath_panel import XPathPanel

SAMPLE_XML = """
<AppiumAUT>
  <Window Name="Test App" AutomationId="win_test">
    <Button Name="Submit" AutomationId="btn_submit" ClassName="WPFButton"/>
  </Window>
</AppiumAUT>
"""


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_toolbar_state_changes(qapp):
    toolbar = Toolbar()
    assert "Disconnected" in toolbar.btn_session.text()

    toolbar.set_session_state("connected", "Notepad.exe")
    assert "Notepad.exe" in toolbar.btn_session.text()


def test_tree_panel_and_attribute_panel_population(qapp):
    root = TreeParser.parse(SAMPLE_XML)
    btn_node = root.children[0].children[0]

    tree_panel = TreePanel()
    tree_panel.populate(root)
    assert tree_panel.tree_widget.topLevelItemCount() == 1

    attr_panel = AttributePanel()
    attr_panel.populate(btn_node)
    assert attr_panel.table.rowCount() >= 3

    # Test collapsible toggle
    assert attr_panel.table.isHidden() is False
    attr_panel.toggle_collapse()
    assert attr_panel.table.isHidden() is True
    assert "Collapsed" in attr_panel.lbl_title.text()
    attr_panel.toggle_collapse()
    assert attr_panel.table.isHidden() is False


def test_tree_deep_search_filtering(qapp):
    root = TreeParser.parse(SAMPLE_XML)
    tree_panel = TreePanel()
    tree_panel.populate(root)

    # Search for node "Submit"
    tree_panel.search_edit.setText("Submit")
    tree_panel._perform_search()
    # Matching item must be instantiated and not hidden
    matching_item = None
    for item in tree_panel._node_item_map.values():
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node and node.name == "Submit":
            matching_item = item
            break

    assert matching_item is not None
    assert matching_item.isHidden() is False

    # Clear search
    tree_panel.search_edit.clear()
    tree_panel._perform_search()
    assert matching_item.isHidden() is False


def test_xpath_panel_generation_and_prefix_toggle(qapp):
    root = TreeParser.parse(SAMPLE_XML)
    lxml_tree = etree.fromstring(SAMPLE_XML.encode())
    btn_node = root.children[0].children[0]

    xpath_panel = XPathPanel()
    xpath_panel.populate(btn_node, tree_root=root, lxml_tree=lxml_tree)
    assert len(xpath_panel._candidates) >= 1
    assert "Button" in xpath_panel._candidates[0].xpath
    assert "Submit" in xpath_panel._candidates[0].xpath

    # Toggle container prefix
    xpath_panel.chk_prefix.setChecked(True)
    assert xpath_panel.chk_prefix.isChecked() is True
    assert xpath_panel._candidates[0].xpath.startswith("//Window")


def test_main_window_assembly(qapp):
    cfg = XGenConfig(auto_connect_on_startup=False)
    win = MainWindow(cfg, start_hooks=False)
    assert win.tree_panel is not None
    assert win.attr_panel is not None
    assert win.xpath_panel is not None
    assert win.toolbar is not None
    assert win.status_bar is not None

    # Test tree fetch complete handler
    root = TreeParser.parse(SAMPLE_XML)
    win._on_tree_fetch_complete("0x0001", SAMPLE_XML, root)
    assert "Tree ready" in win.status_bar.lbl_msg.text()

    # Test clicking [Select in Tree] on a node from XPathPanel drawer
    btn_node = root.children[0].children[0]
    win._on_xpath_node_selected(btn_node)
    assert win.attr_panel.table.rowCount() > 0

    win.session_manager.close()
    win.tree_fetcher.close()
    win.close()


def test_legend_dialog_initialization(qapp):
    from xgen.ui.legend_dialog import LegendDialog
    dlg = LegendDialog()
    assert dlg.windowTitle() == "xGen — XPath Guide & Index"
    dlg.close()


def test_xpath_card_test_and_click_signals(qapp):
    root = TreeParser.parse(SAMPLE_XML)
    lxml_tree = etree.fromstring(SAMPLE_XML.encode())
    btn_node = root.children[0].children[0]

    xpath_panel = XPathPanel()
    xpath_panel.populate(btn_node, tree_root=root, lxml_tree=lxml_tree)
    assert len(xpath_panel._cards) >= 1

    card = xpath_panel._cards[0]
    test_signals = []
    click_signals = []
    hover_signals = []
    type_signals = []

    xpath_panel.test_requested.connect(lambda xp, c: test_signals.append((xp, c)))
    xpath_panel.click_requested.connect(lambda xp, c: click_signals.append((xp, c)))
    xpath_panel.hover_requested.connect(lambda xp, c: hover_signals.append((xp, c)))
    xpath_panel.type_requested.connect(lambda xp, t, c: type_signals.append((xp, t, c)))

    # Test clicking Test button
    card.btn_test.click()
    assert len(test_signals) == 1
    assert test_signals[0][0] == card.candidate.xpath
    assert test_signals[0][1] == card

    # Test clicking Click button after showing test result
    card.show_test_result(True, 12.0)
    assert card.btn_click.isHidden() is False
    assert card.btn_hover.isHidden() is False
    assert card.btn_type.isHidden() is False

    card.btn_click.click()
    assert len(click_signals) == 1
    assert click_signals[0][0] == card.candidate.xpath
    assert click_signals[0][1] == card

    card.btn_hover.click()
    assert len(hover_signals) == 1
    assert hover_signals[0][0] == card.candidate.xpath
    assert hover_signals[0][1] == card

    # Test inline typing
    card.btn_type.click()
    assert card.type_bar.isHidden() is False
    card.input_type_text.setText("Hello World")
    card.btn_submit_type.click()
    assert len(type_signals) == 1
    assert type_signals[0][0] == card.candidate.xpath
    assert type_signals[0][1] == "Hello World"
    assert type_signals[0][2] == card
