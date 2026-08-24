"""
Unit tests for XPathGenerator, StabilityScorer, and XPathVerifier.
"""

import pytest
from lxml import etree
from xgen.core.stability_scorer import StabilityScorer
from xgen.core.tree_parser import TreeParser
from xgen.core.xpath_generator import XPathGenerator, XPathTier
from xgen.core.xpath_verifier import XPathVerifier

SAMPLE_XML = """
<AppiumAUT>
  <Window Name="Main Window" AutomationId="win_main">
    <Pane Name="Login Pane" AutomationId="pane_login">
      <!-- Unique AutomationId -->
      <Button Name="Submit" AutomationId="btn_submit" ClassName="WPFButton"/>
      
      <!-- Duplicate names and tags -->
      <Button Name="Duplicate" ClassName="WPFButton"/>
      <Button Name="Duplicate" ClassName="WPFButton"/>
      
      <!-- Numeric AutomationId (WinForms style) -->
      <Edit Name="Username" AutomationId="1001" ClassName="TextBox"/>

      <!-- Quotes in Name -->
      <Button Name="He said &quot;Hello&quot;" AutomationId="btn_quotes"/>
    </Pane>
  </Window>
</AppiumAUT>
"""


@pytest.fixture
def parsed_data():
    root = TreeParser.parse(SAMPLE_XML)
    lxml_tree = etree.fromstring(SAMPLE_XML.encode("utf-8"))
    return root, lxml_tree


def test_tier1_and_tier2_generation_for_stable_id(parsed_data):
    root, lxml_tree = parsed_data
    btn_submit = TreeParser.find_by_runtime_id(root, "") or root.children[0].children[0].children[0]
    assert btn_submit.automation_id == "btn_submit"

    gen = XPathGenerator(localization_enabled=True)
    candidates = gen.generate(btn_submit, tree_root=root)

    t1 = next((c for c in candidates if c.tier == XPathTier.T1_TYPE_NAME), None)
    assert t1 is not None
    assert t1.xpath == "//Button[@Name='Submit']"

    t5 = next((c for c in candidates if c.tier == XPathTier.T5_TYPE_AUTO_ID), None)
    assert t5 is not None
    assert t5.xpath == "//Button[@AutomationId='btn_submit']"

    t6 = next((c for c in candidates if c.tier == XPathTier.T6_AUTO_ID), None)
    assert t6 is not None
    assert t6.xpath == "//*[@AutomationId='btn_submit']"

    # Verify uniqueness
    verified = XPathVerifier.verify_batch(candidates, lxml_tree)
    assert verified[0].verify_result.is_unique is True
    assert verified[0].stability_label == "🟢 Stable"


def test_numeric_automation_id_exclusion(parsed_data):
    root, lxml_tree = parsed_data
    # 1001 edit box
    edit_box = root.children[0].children[0].children[3]
    assert edit_box.automation_id == "1001"

    gen = XPathGenerator()
    candidates = gen.generate(edit_box, tree_root=root)

    # Pure numeric ID should NOT generate AutomationId tiers
    assert not any(c.tier in (XPathTier.T5_TYPE_AUTO_ID, XPathTier.T6_AUTO_ID) for c in candidates)
    # Should fall back to Tier 1/2 Name or Ancestor
    assert any(c.tier in (XPathTier.T1_TYPE_NAME, XPathTier.T2_NAME, XPathTier.T4_ANCESTOR_RELATIVE) for c in candidates)


def test_duplicate_elements_and_ancestor_tier(parsed_data):
    root, lxml_tree = parsed_data
    # First Duplicate button
    dup1 = root.children[0].children[0].children[1]
    assert dup1.name == "Duplicate"

    gen = XPathGenerator()
    candidates = gen.generate(dup1, tree_root=root)

    verified = XPathVerifier.verify_batch(candidates, lxml_tree)

    # //*[@Name='Duplicate'] has 2 matches -> multi
    t2 = next(c for c in verified if c.tier == XPathTier.T2_NAME)
    assert t2.verify_result.status == "multi"
    assert t2.verify_result.match_count == 2

    # Tier 10 (positional ancestor) should resolve uniquely
    t10 = next((c for c in verified if c.tier == XPathTier.T10_ANCESTOR_INDEX), None)
    if t10:
        assert t10.verify_result.is_unique is True


def test_quotes_in_name_attribute(parsed_data):
    root, lxml_tree = parsed_data
    quote_btn = root.children[0].children[0].children[4]
    assert 'He said "Hello"' in quote_btn.name

    gen = XPathGenerator()
    candidates = gen.generate(quote_btn, tree_root=root)

    verified = XPathVerifier.verify_batch(candidates, lxml_tree)
    t2 = next(c for c in verified if c.tier == XPathTier.T2_NAME)
    assert t2.verify_result.is_unique is True


def test_stability_scorer_ratings():
    node_stable = TreeParser.parse("<AppiumAUT><Button AutomationId='btn_save'/></AppiumAUT>").children[0]
    score, label, loc, pos = StabilityScorer.score("//*[@AutomationId='btn_save']", node_stable)
    assert score == 65
    assert label == "🟡 Moderate"
    assert loc is False

    node_loc = TreeParser.parse("<AppiumAUT><Button Name='Save'/></AppiumAUT>").children[0]
    score, label, loc, pos = StabilityScorer.score("//*[@Name='Save']", node_loc)
    assert score == 70
    assert label == "🟡 Moderate"
    assert loc is True

    # Explicit ControlType Button gets +5 specificity bonus -> 80 pts (🟢 Stable)
    score_btn, label_btn, _, _ = StabilityScorer.score("//Button[@Name='Save']", node_loc)
    assert score_btn == 80
    assert label_btn == "🟢 Stable"

    node_pos = TreeParser.parse("<AppiumAUT><Button/></AppiumAUT>").children[0]
    score, label, loc, pos = StabilityScorer.score("//*[@AutomationId='win']//Button[3]", node_pos)
    assert pos is True
    assert score < 60


def test_ancestor_climbing_multi_window_desktop():
    xml = """<Pane Name='Desktop 1'>
      <Window Name='MINGW64:/e/projects/xGen' ClassName='mintty'>
        <TitleBar AutomationId='TitleBar'>
          <Button Name='Minimize'/>
          <Button Name='Close'/>
        </TitleBar>
      </Window>
      <Window Name='Notepad' ClassName='Notepad'>
        <TitleBar AutomationId='TitleBar'>
          <Button Name='Minimize'/>
          <Button Name='Close'/>
        </TitleBar>
      </Window>
    </Pane>"""
    root = TreeParser.parse(xml)
    from lxml import etree
    lxml_elem = etree.fromstring(xml.encode("utf-8"))

    # Select Minimize button in MINGW64 window
    target_btn = root.children[0].children[0].children[0]
    assert target_btn.name == "Minimize"

    gen = XPathGenerator()
    candidates = gen.generate(target_btn, tree_root=root)
    verified = XPathVerifier.verify_batch(candidates, lxml_elem)

    # Top candidate MUST be unique (1 match) with window/ancestor scope
    assert verified[0].verify_result.is_unique is True
    assert verified[0].verify_result.match_count == 1
    assert "Window" in verified[0].xpath
    assert "Button" in verified[0].xpath


def test_multi_match_indexed_disambiguation_and_ordering():
    # Two identical windows open (like 2 Git Bash terminals)
    xml = """<Pane Name='Desktop 1'>
      <Window Name='MINGW64:/e/projects/xGen' ClassName='mintty'>
        <TitleBar AutomationId='TitleBar'>
          <Button Name='Minimize'/>
        </TitleBar>
      </Window>
      <Window Name='MINGW64:/e/projects/xGen' ClassName='mintty'>
        <TitleBar AutomationId='TitleBar'>
          <Button Name='Minimize'/>
        </TitleBar>
      </Window>
    </Pane>"""
    root = TreeParser.parse(xml)
    node_map = {}
    lxml_elem = TreeParser.to_xml_element(root, node_map)

    # Select the Minimize button on the SECOND terminal window
    target_btn2 = root.children[1].children[0].children[0]
    assert target_btn2.name == "Minimize"

    gen = XPathGenerator()
    candidates = gen.generate(target_btn2, tree_root=root)
    verified = XPathVerifier.verify_batch(candidates, lxml_elem, target_node=target_btn2, node_map=node_map)

    # 1. Multi-match candidates must have ordered matched_nodes
    t2 = next(c for c in verified if c.tier == XPathTier.T2_NAME)
    assert t2.verify_result.match_count == 2
    assert len(t2.verify_result.matched_nodes) == 2
    assert t2.verify_result.matched_nodes[0] == root.children[0].children[0].children[0]
    # 2. An indexed disambiguation candidate MUST be generated for target_btn2 (index 2)
    indexed_unique = [c for c in verified if c.tier == XPathTier.T9_INDEXED_DISAMBIGUATION and c.verify_result.is_unique]
    assert len(indexed_unique) >= 1
    assert "[2]" in indexed_unique[0].xpath
    assert indexed_unique[0].verify_result.match_count == 1


def test_list_item_child_scoping_and_false_positive_exclusion():
    xml = """
    <Window Name='projects'>
      <Header Name='Header'>
        <SplitButton Name='Name' AutomationId='System.ItemNameDisplay'/>
      </Header>
      <List Name='Items View'>
        <ListItem Name='Alemeno'>
          <Edit Name='Name' AutomationId='System.ItemNameDisplay'/>
        </ListItem>
        <ListItem Name='Contact-CSV-Cleaner'>
          <Edit Name='Name' AutomationId='System.ItemNameDisplay'/>
        </ListItem>
      </List>
    </Window>"""
    root = TreeParser.parse(xml)
    node_map = {}
    lxml_elem = TreeParser.to_xml_element(root, node_map)

    # User clicks the Edit inside "Contact-CSV-Cleaner"
    target_edit = root.children[1].children[1].children[0]
    assert target_edit.tag == "Edit"
    assert target_edit.name == "Name"
    assert target_edit.parent.name == "Contact-CSV-Cleaner"

    gen = XPathGenerator()
    candidates = gen.generate(target_edit, tree_root=root)
    verified = XPathVerifier.verify_batch(candidates, lxml_elem, target_node=target_edit, node_map=node_map)

    # 1. No SplitButton selector should be considered unique/valid for target_edit
    for c in verified:
        if "SplitButton" in c.xpath:
            assert not (c.verify_result and c.verify_result.is_unique)

    # 2. The top recommended selector must be scoped to ListItem[@Name='Contact-CSV-Cleaner']
    unique_candidates = [c for c in verified if c.verify_result and c.verify_result.is_unique and not c.is_diagnostic_only]
    assert len(unique_candidates) >= 1
    top_c = unique_candidates[0]
    assert "Contact-CSV-Cleaner" in top_c.xpath
    assert "Edit" in top_c.xpath

