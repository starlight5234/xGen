"""
Stability Scorer for XPath candidate selectors (xGen v3).
Evaluates maintainability, attribute durability, localization risk, positional ceilings,
and origin bridge confidence.
"""

from __future__ import annotations

import re
from typing import Set, Tuple

from xgen.core.tree_parser import UINode
from xgen.core.volatility_classifier import NumericContext, VolatilityClassifier, VolatilityVerdict


class StabilityScorer:
    """Calculates stability scores and visual ratings for XPath selectors."""

    # Positional index pattern: e.g. [1], [2], [10]
    INDEX_PATTERN = re.compile(r"\[\d+\]")

    @classmethod
    def score(
        cls,
        xpath: str,
        node: UINode,
        localization_enabled: bool = True,
        is_data_dependent: bool = False,
    ) -> Tuple[int, str, bool, bool]:
        """
        Compute stability score (0-100), rating label, localization_risk flag, and positional flag.
        Returns (score, label, localization_risk, is_positional).
        """
        loc_risk = False
        is_positional = bool(cls.INDEX_PATTERN.search(xpath))

        auto_id = node.automation_id
        name = node.name
        is_ancestor_scoped = "//" in xpath[2:]

        # 1. Attribute-based base scoring: Prioritize semantic human-readable Names over build-volatile AutomationIds
        if "@Name=" in xpath or "starts-with(@Name" in xpath or "contains(@Name" in xpath or "@HelpText=" in xpath:
            loc_risk = True
            if name:
                ctx = VolatilityClassifier.classify_numeric_name(name)
                if ctx == NumericContext.ORDINAL_LABEL:
                    base_val = 80 if any(ch.isdigit() for ch in name) else 85
                elif ctx == NumericContext.UNKNOWN_NUMERIC:
                    base_val = 65
                elif ctx in (NumericContext.COUNTER, NumericContext.TIMESTAMP, NumericContext.LIVE_VALUE):
                    base_val = 35
                else:
                    base_val = 85
            else:
                base_val = 65
            score = base_val + (10 if is_ancestor_scoped else 0)
        elif auto_id and f"@AutomationId=" in xpath:
            verdict = VolatilityClassifier.classify_id_volatility(auto_id)
            if verdict == VolatilityVerdict.STATIC:
                score = 70 if not is_ancestor_scoped else 65
            elif verdict == VolatilityVerdict.SUSPECT:
                score = 50
            else:
                score = 30
        elif "@HelpText=" in xpath:
            score = 65 + (10 if is_ancestor_scoped else 0)
        elif "@ClassName=" in xpath or "contains(@ClassName" in xpath:
            score = 60 + (10 if is_ancestor_scoped else 0)
        else:
            score = 45

        # 2. Modifiers
        # ControlType Specificity vs Wildcard Penalty
        has_wildcard = "/*[" in xpath or xpath.startswith("//*") or "//*[" in xpath
        if not has_wildcard and node.tag and node.tag in xpath:
            score += 5  # Bonus for explicit ControlType specificity
        elif has_wildcard:
            score -= 5  # Penalty for generic wildcard *

        if is_positional:
            score -= 15

        depth = xpath.count("/")
        if depth > 6:
            score -= 10

        if loc_risk and localization_enabled:
            score -= 10

        # 3. Hard Band Ceilings (v3 guarantees)
        # Positional selectors can never be "🟢 Stable"
        if is_positional:
            score = min(score, 74)

        # Positional selectors in repeating list/data containers can never even be "🟡 Moderate"
        if is_positional and is_data_dependent:
            score = min(score, 49)

        # Bridge confidence cap (low confidence inspections ceiling score)
        conf = getattr(node, "bridge_confidence", 1.0)
        score = min(score, int(40 + 60 * conf))

        # Normalize score
        score = max(5, min(100, score))

        # Label assignment
        if score >= 75:
            label = "🟢 Stable"
        elif score >= 50:
            label = "🟡 Moderate"
        else:
            label = "🔴 Fragile"

        return (score, label, loc_risk, is_positional)
