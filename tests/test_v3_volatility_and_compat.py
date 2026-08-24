"""
Unit tests for xGen v3 Volatility Classifiers, Hard Band Ceilings, and Appium Compatibility.
"""

import pytest
from xgen.core.appium_compat import AppiumXPathCompatLayer
from xgen.core.stability_scorer import StabilityScorer
from xgen.core.tree_parser import UINode
from xgen.core.volatility_classifier import (
    NumericContext,
    VolatilityClassifier,
    VolatilityVerdict,
)
from xgen.core.xpath_generator import XPathGenerator, XPathTier


def test_id_volatility_classifier():
    # Pure integers -> VOLATILE
    assert VolatilityClassifier.classify_id_volatility("12345") == VolatilityVerdict.VOLATILE

    # React useId -> VOLATILE
    assert VolatilityClassifier.classify_id_volatility(":r0:") == VolatilityVerdict.VOLATILE
    assert VolatilityClassifier.classify_id_volatility(":r1a:") == VolatilityVerdict.VOLATILE

    # Framework auto IDs -> VOLATILE
    assert VolatilityClassifier.classify_id_volatility("el_183920") == VolatilityVerdict.VOLATILE
    assert VolatilityClassifier.classify_id_volatility("item-999") == VolatilityVerdict.VOLATILE

    # Bare long hex runs -> VOLATILE
    assert VolatilityClassifier.classify_id_volatility("deadbeef012345") == VolatilityVerdict.VOLATILE

    # GUIDs -> SUSPECT
    assert VolatilityClassifier.classify_id_volatility("e3b0c442-98fc-1c14-9afb-4c8996fb9242") == VolatilityVerdict.SUSPECT

    # Clean static IDs -> STATIC
    assert VolatilityClassifier.classify_id_volatility("btn_save_document") == VolatilityVerdict.STATIC
    assert VolatilityClassifier.classify_id_volatility("headerTitle") == VolatilityVerdict.STATIC
    assert VolatilityClassifier.classify_id_volatility("login_button") == VolatilityVerdict.STATIC


def test_numeric_token_classifier():
    # Counters -> COUNTER
    assert VolatilityClassifier.classify_numeric_name("Item 47 of 312") == NumericContext.COUNTER
    assert VolatilityClassifier.classify_numeric_name("Page 1 of 5") == NumericContext.COUNTER

    # Timestamps -> TIMESTAMP
    assert VolatilityClassifier.classify_numeric_name("Last synced at 12:45:00") == NumericContext.TIMESTAMP
    assert VolatilityClassifier.classify_numeric_name("14:30") == NumericContext.TIMESTAMP

    # Live Values -> LIVE_VALUE
    assert VolatilityClassifier.classify_numeric_name("Total: $19.99") == NumericContext.LIVE_VALUE
    assert VolatilityClassifier.classify_numeric_name("€45.50") == NumericContext.LIVE_VALUE

    # Ordinal Labels -> ORDINAL_LABEL
    assert VolatilityClassifier.classify_numeric_name("Page 2") == NumericContext.ORDINAL_LABEL
    assert VolatilityClassifier.classify_numeric_name("Tab 1") == NumericContext.ORDINAL_LABEL
    assert VolatilityClassifier.classify_numeric_name("Document 3") == NumericContext.ORDINAL_LABEL


def test_stable_substring_extraction():
    # Dynamic title with delimiter
    sub = VolatilityClassifier.extract_stable_substring("xGen - Antigravity IDE - Review")
    assert sub == "xGen"

    sub_term = VolatilityClassifier.extract_stable_substring("MINGW64:/c/Users/Dev/projects")
    assert sub_term == "MINGW64"

    # Word-boundary snapping
    sub_words = VolatilityClassifier.extract_stable_substring("Backend Internship Assignment")
    assert sub_words == "Backend Internship"

    # Trivial tokens rejected
    assert VolatilityClassifier.extract_stable_substring("OK") is None
    assert VolatilityClassifier.extract_stable_substring("Add") is None


def test_starts_with_and_contains_name_stability_scoring():
    node = UINode(tag="Button", attributes={"Name": "Submit Form"}, bridge_confidence=1.0)
    # starts-with(@Name) must score same as @Name= (85 base + 5 type bonus - 10 loc = 80 pts)
    score_sw, label_sw, loc_sw, _ = StabilityScorer.score("//Button[starts-with(@Name, 'Submit')]", node)
    assert score_sw == 80
    assert label_sw == "🟢 Stable"
    assert loc_sw is True

    # contains(@Name) must also score properly
    score_ct, label_ct, loc_ct, _ = StabilityScorer.score("//Button[contains(@Name, 'Submit')]", node)
    assert score_ct == 80
    assert label_ct == "🟢 Stable"
    assert loc_ct is True


def test_helptext_and_classname_only_fallbacks():
    # Anonymous control with only ClassName
    node_cls = UINode(tag="Pane", attributes={"ClassName": "SystemListView32"})
    gen = XPathGenerator()
    cands_cls = gen.generate(node_cls)
    t8 = next((c for c in cands_cls if c.tier == XPathTier.T8_TYPE_NAME_CLASS), None)
    assert t8 is not None
    assert t8.xpath == "//Pane[@ClassName='SystemListView32']"

    # Control with HelpText but no Name
    node_help = UINode(tag="Button", attributes={"HelpText": "Click to save your progress"})
    cands_help = gen.generate(node_help)
    t7 = next((c for c in cands_help if "@HelpText=" in c.xpath), None)
    assert t7 is not None
    assert "HelpText" in t7.xpath
    assert t7.localization_risk is True


def test_tier_enum_no_collision():
    assert XPathTier.T11_ABSOLUTE_PATH.value == 110
    assert XPathTier.T1A_TYPE_NAME_STARTS_WITH.value == 15
    assert XPathTier.T11_ABSOLUTE_PATH.value != XPathTier.T1A_TYPE_NAME_STARTS_WITH.value


def test_stability_scorer_v3_hard_ceilings():
    node = UINode(
        tag="Button",
        attributes={"AutomationId": "btn_save", "Name": "Save"},
        bridge_confidence=1.0
    )

    # 1. Standard ControlType + Name -> 80 pts (🟢 Stable: 85 base + 5 ControlType bonus - 10 localization)
    score, label, loc_risk, is_pos = StabilityScorer.score("//Button[@Name='Save']", node)
    assert score == 80
    assert label == "🟢 Stable"
    assert is_pos is False

    # 2. ControlType + AutomationId -> 75 pts (🟢 Stable: 70 base + 5 ControlType bonus)
    score_id, label_id, _, _ = StabilityScorer.score("//Button[@AutomationId='btn_save']", node)
    assert score_id == 75
    assert label_id == "🟢 Stable"

    # 3. Wildcard AutomationId -> 65 pts (🟡 Moderate: 70 base - 5 wildcard penalty)
    score_wild, label_wild, _, _ = StabilityScorer.score("//*[@AutomationId='btn_save']", node)
    assert score_wild == 65
    assert label_wild == "🟡 Moderate"

    # 4. Positional selector -> Hard ceiling at 74 pts (🟡 Moderate, can NEVER be 🟢 Stable)
    score_pos, label_pos, _, is_pos = StabilityScorer.score("(//Button[@Name='Save'])[1]", node)
    assert score_pos <= 74
    assert label_pos == "🟡 Moderate"
    assert is_pos is True

    # 3. Positional in repeating list container -> Hard ceiling at 49 pts (🔴 Fragile, can NEVER be 🟡 Moderate)
    score_list, label_list, _, _ = StabilityScorer.score(
        "(//ListItem[@Name='Row'])[1]",
        node,
        is_data_dependent=True
    )
    assert score_list <= 49
    assert label_list == "🔴 Fragile"

    # 4. Low bridge confidence (0.4) -> Score ceiling: min(raw, 40 + 60*0.4 = 64)
    low_conf_node = UINode(
        tag="Button",
        attributes={"AutomationId": "btn_save", "Name": "Save"},
        bridge_confidence=0.4
    )
    score_low, label_low, _, _ = StabilityScorer.score("//Button[@AutomationId='btn_save']", low_conf_node)
    assert score_low <= 64
    assert score_low != 100


def test_appium_xpath_compat_layer():
    # Valid XPath 1.0 selectors
    assert AppiumXPathCompatLayer.is_appium_compatible("//Button[@AutomationId='btn_ok']") is True
    assert AppiumXPathCompatLayer.is_appium_compatible("(//Window[@Name='App']//Button)[1]") is True
    assert AppiumXPathCompatLayer.is_appium_compatible("//Button[starts-with(@Name, 'Save') and @ClassName='WPFButton']") is True

    # Disallowed unbounded axes
    assert AppiumXPathCompatLayer.is_appium_compatible("//Button/following::Button") is False
    assert AppiumXPathCompatLayer.is_appium_compatible("//Button/preceding::Button") is False

    # Disallowed XPath 2.0+ functions
    assert AppiumXPathCompatLayer.is_appium_compatible("//Button[matches(@Name, '^[0-9]+$')]") is False
    assert AppiumXPathCompatLayer.is_appium_compatible("//Button[lower-case(@Name)='save']") is False

    # Normalization
    raw = " ( //Window[starts-with(@Name,'App')]//Button ) [2] "
    normalized = AppiumXPathCompatLayer.normalize_readability(raw)
    assert normalized == "(//Window[starts-with(@Name, 'App')]//Button)[2]"
