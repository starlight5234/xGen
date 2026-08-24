"""
Unit tests for Rect, XPath escaping, and utility functions.
"""

import pytest
from xgen.utils.rect import Rect
from xgen.utils.xpath_escape import escape_xpath_literal


def test_rect_dimensions_and_containment():
    r = Rect(left=100, top=200, right=300, bottom=400)
    assert r.width == 200
    assert r.height == 200
    assert r.area == 40000

    assert r.contains_point(100, 200) is True
    assert r.contains_point(200, 300) is True
    assert r.contains_point(50, 200) is False
    assert r.contains_point(301, 400) is False


def test_rect_from_appium_string():
    r1 = Rect.from_appium_string("[100,200][250,230]")
    assert r1 is not None
    assert r1.left == 100
    assert r1.top == 200
    assert r1.right == 250
    assert r1.bottom == 230

    r2 = Rect.from_appium_string("[-10, -20][100, 200]")
    assert r2 is not None
    assert r2.left == -10
    assert r2.top == -20

    assert Rect.from_appium_string("") is None
    assert Rect.from_appium_string("invalid") is None


def test_xpath_escape_literal():
    # Simple without quotes
    assert escape_xpath_literal("Submit") == "'Submit'"

    # With single quote
    assert escape_xpath_literal("O'Brien") == '"O\'Brien"'

    # With double quote
    assert escape_xpath_literal('He said "Hello"') == "'He said \"Hello\"'"

    # With both single and double quotes
    both = 'He said "Hello", don\'t you?'
    escaped = escape_xpath_literal(both)
    assert escaped.startswith("concat(")
    assert "'\"'" in escaped or "\"'" in escaped
