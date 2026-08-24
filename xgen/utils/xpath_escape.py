"""
XPath string literal escaping for XPath 1.0.
Handles single and double quotes cleanly according to XPath 1.0 standard.
"""

from __future__ import annotations


def escape_xpath_literal(s: str) -> str:
    """
    Format a string literal for use in an XPath 1.0 predicate.
    - If string contains no single quotes, wraps in '...': 'Submit' -> "'Submit'"
    - If string contains single quotes but no double quotes, wraps in "...": "O'Brien" -> '"O\'Brien"'
    - If string contains both, uses XPath 1.0 concat(): 'He said "Hello", don'\''t you?'
      -> concat('He said "', '"', 'Hello', '"', ', don', "'", 't you?')
    """
    if "'" not in s:
        return f"'{s}'"
    if '"' not in s:
        return f'"{s}"'

    # String contains both single and double quotes
    parts = []
    current = []
    for ch in s:
        if ch == "'":
            if current:
                parts.append(f"'{''.join(current)}'")
                current = []
            parts.append("\"'\"")
        elif ch == '"':
            if current:
                parts.append(f"'{''.join(current)}'")
                current = []
            parts.append("'\"'")
        else:
            current.append(ch)

    if current:
        parts.append(f"'{''.join(current)}'")

    return f"concat({', '.join(parts)})"
