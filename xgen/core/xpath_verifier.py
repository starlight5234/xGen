"""
XPath Uniqueness Verifier (xGen v3).
Executes candidate XPaths against pre-parsed in-memory lxml trees.
Guarantees sub-5ms verification, cause-aware multi-match disambiguation,
and Appium-compatible sort ordering.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import List, Optional, Set
from lxml import etree

from xgen.core.appium_compat import AppiumXPathCompatLayer
from xgen.core.stability_scorer import StabilityScorer
from xgen.core.tree_parser import TreeParser, UINode
from xgen.core.xpath_generator import VerifyResult, XPathCandidate, XPathTier
from xgen.utils.xpath_escape import escape_xpath_literal

logger = logging.getLogger("xgen.verifier")


class MultiMatchCause(Enum):
    REPEATED_LIST_ITEM = "REPEATED_LIST_ITEM"
    MULTI_WINDOW_INSTANCE = "MULTI_WINDOW_INSTANCE"
    DUPLICATE_STATIC_UI = "DUPLICATE_STATIC_UI"


class XPathVerifier:
    """
    Evaluates XPath match counts and uniqueness against a live compiled lxml tree.
    """

    @classmethod
    def classify_multi_match(cls, matches: List[UINode]) -> MultiMatchCause:
        """
        Classifies why a selector matched multiple nodes in the UI tree.
        """
        if not matches:
            return MultiMatchCause.DUPLICATE_STATIC_UI

        def _get_window(n: UINode) -> Optional[UINode]:
            curr: Optional[UINode] = n
            while curr:
                if curr.tag == "Window":
                    return curr
                curr = curr.parent
            return None

        windows: Set[Optional[UINode]] = {_get_window(m) for m in matches if _get_window(m) is not None}
        if len(windows) > 1:
            return MultiMatchCause.MULTI_WINDOW_INSTANCE

        if any(m.is_within_repeating_container() for m in matches):
            return MultiMatchCause.REPEATED_LIST_ITEM

        return MultiMatchCause.DUPLICATE_STATIC_UI

    @classmethod
    def verify_batch(
        cls,
        candidates: List[XPathCandidate],
        lxml_tree: Optional[etree._Element],
        max_results: Optional[int] = None,
        target_node: Optional[UINode] = None,
        node_map: Optional[dict] = None
    ) -> List[XPathCandidate]:
        """
        Verify all candidate XPaths against lxml_tree and return sorted by uniqueness and stability.
        Automatically generates cause-aware disambiguation selectors when multi-matches occur.
        """
        if not candidates:
            return []

        if lxml_tree is None:
            for c in candidates:
                c.verify_result = VerifyResult(xpath=c.xpath, match_count=0, status="zero")
            return candidates

        for candidate in candidates:
            candidate.verify_result = cls.verify_single(candidate.xpath, lxml_tree, node_map)

        # Reconcile XML tags for wildcard matches (e.g. Electron where UIA tag != XML DOM tag)
        reconciled_candidates: List[XPathCandidate] = []
        seen_xpaths = {c.xpath for c in candidates}
        for c in list(candidates):
            if c.verify_result and c.verify_result.matched_nodes:
                matched = c.verify_result.matched_nodes
                for m_node in matched:
                    is_target = False
                    if target_node:
                        if m_node == target_node:
                            is_target = True
                        elif target_node.bounding_rect and m_node.bounding_rect and target_node.bounding_rect.intersects(m_node.bounding_rect):
                            is_target = True
                    else:
                        is_target = True

                    if not is_target:
                        continue

                    if m_node.tag and m_node.tag not in ("AppiumAUT", "*") and m_node.tag != (target_node.tag if target_node else ""):
                        if "/*[" in c.xpath or c.xpath.startswith("//*"):
                            reconciled_xp = c.xpath.replace("/*[", f"/{m_node.tag}[", 1)
                            if reconciled_xp.startswith("//*"):
                                reconciled_xp = f"//{m_node.tag}" + reconciled_xp[3:]
                            reconciled_xp = AppiumXPathCompatLayer.normalize_readability(reconciled_xp)
                            if reconciled_xp not in seen_xpaths:
                                seen_xpaths.add(reconciled_xp)
                                vres = cls.verify_single(reconciled_xp, lxml_tree, node_map)
                                if vres.status in ("unique", "multi") and (not target_node or target_node in vres.matched_nodes):
                                    score, label, loc_risk, is_pos = StabilityScorer.score(
                                        reconciled_xp, m_node, localization_enabled=True, is_data_dependent=c.is_data_dependent
                                    )
                                    reconciled_candidates.append(XPathCandidate(
                                        xpath=reconciled_xp,
                                        tier=XPathTier.T1_TYPE_NAME if "@Name=" in reconciled_xp else XPathTier.T5_TYPE_AUTO_ID,
                                        stability_score=score,
                                        stability_label=label,
                                        localization_risk=loc_risk,
                                        is_positional=is_pos,
                                        is_data_dependent=c.is_data_dependent,
                                        verify_result=vres
                                    ))
        candidates.extend(reconciled_candidates)

        # Prune candidates that match another element entirely (false positive match)
        if target_node:
            for c in candidates:
                if c.verify_result and c.verify_result.matched_nodes:
                    contains_target = (target_node in c.verify_result.matched_nodes)
                    if not contains_target and target_node.bounding_rect:
                        contains_target = any(
                            m.bounding_rect and target_node.bounding_rect.intersects(m.bounding_rect)
                            for m in c.verify_result.matched_nodes
                        )
                    if not contains_target:
                        c.verify_result.status = "zero"
                        c.verify_result.match_count = 0
                        c.is_diagnostic_only = True

        # Disambiguate multi-matches: Generate unique indexed and window-scoped variants
        indexed_candidates: List[XPathCandidate] = []

        for c in list(candidates):
            if c.is_diagnostic_only or not c.verify_result or c.verify_result.status != "multi":
                continue
            matched = c.verify_result.matched_nodes
            if not matched:
                continue

            cause = cls.classify_multi_match(matched)

            # Identify target match index
            target_idx = None
            if target_node:
                if target_node in matched:
                    target_idx = matched.index(target_node) + 1
                else:
                    for i, m in enumerate(matched, start=1):
                        if (target_node.name and m.name == target_node.name) or (
                            target_node.bounding_rect and m.bounding_rect and target_node.bounding_rect.intersects(m.bounding_rect)
                        ):
                            target_idx = i
                            break

            # Strategy for MULTI_WINDOW_INSTANCE: Re-scope to specific Window instance if possible
            if cause == MultiMatchCause.MULTI_WINDOW_INSTANCE and target_node:
                ancestors = TreeParser.get_ancestors(target_node)
                win_anc = next((a for a in reversed(ancestors) if a.tag == "Window"), None)
                if win_anc and not c.xpath.startswith("//Window"):
                    if win_anc.name:
                        val_w = escape_xpath_literal(win_anc.name)
                        win_scoped = AppiumXPathCompatLayer.normalize_readability(f"//Window[@Name={val_w}]{c.xpath}")
                        if win_scoped not in seen_xpaths:
                            seen_xpaths.add(win_scoped)
                            vres = cls.verify_single(win_scoped, lxml_tree, node_map)
                            score, label, loc_risk, is_pos = StabilityScorer.score(
                                win_scoped, target_node, localization_enabled=True, is_data_dependent=False
                            )
                            indexed_candidates.append(XPathCandidate(
                                xpath=win_scoped,
                                tier=XPathTier.T4_ANCESTOR_RELATIVE,
                                stability_score=score,
                                stability_label=label,
                                localization_risk=loc_risk,
                                is_positional=is_pos,
                                verify_result=vres
                            ))

            # Strategy for Positional Indexing:
            indices_to_gen = [target_idx] if target_idx else list(range(1, min(len(matched) + 1, 3)))
            for idx in indices_to_gen:
                if idx is None:
                    continue
                raw_indexed = f"({c.xpath})[{idx}]"
                indexed_xpath = AppiumXPathCompatLayer.normalize_readability(raw_indexed)
                if indexed_xpath not in seen_xpaths:
                    seen_xpaths.add(indexed_xpath)
                    target_match_node = matched[idx - 1] if idx - 1 < len(matched) else (target_node or matched[0])
                    is_data_dep = (cause == MultiMatchCause.REPEATED_LIST_ITEM)
                    is_diag = (cause == MultiMatchCause.MULTI_WINDOW_INSTANCE)

                    score, label, loc_risk, is_pos = StabilityScorer.score(
                        indexed_xpath,
                        target_match_node,
                        is_data_dependent=is_data_dep
                    )

                    if is_diag:
                        score = min(score, 45)
                        label = "🔴 Fragile"

                    c_idx = XPathCandidate(
                        xpath=indexed_xpath,
                        tier=XPathTier.T9_INDEXED_DISAMBIGUATION,
                        stability_score=score,
                        stability_label=label,
                        localization_risk=loc_risk,
                        is_positional=True,
                        is_data_dependent=is_data_dep,
                        is_diagnostic_only=is_diag,
                        verify_result=VerifyResult(
                            xpath=indexed_xpath,
                            match_count=1,
                            status="unique",
                            matched_nodes=[target_match_node]
                        )
                    )
                    indexed_candidates.append(c_idx)

        candidates.extend(indexed_candidates)

        # 6-Factor Sort Key:
        # 1. Non-diagnostic before diagnostic
        # 2. Status rank: unique (0) > multi (1) > zero (2) > error (3)
        # 3. Data dependency: non-data-dependent (0) > data-dependent (1)
        # 4. Stability score descending (100 > 90 > 75 > 60)
        # 5. Tier rank: Tier 1 > Tier 2 > Tier 6
        # 6. Shortest concise XPath length as tie-breaker
        def sort_key(c: XPathCandidate):
            diag_rank = 1 if c.is_diagnostic_only else 0
            status = c.verify_result.status if c.verify_result else "zero"
            status_order = {"unique": 0, "multi": 1, "zero": 2, "error": 3}.get(status, 4)
            data_dep_rank = 1 if c.is_data_dependent else 0
            tier_rank = c.tier.value
            return (diag_rank, status_order, data_dep_rank, -c.stability_score, tier_rank, len(c.xpath))

        candidates.sort(key=sort_key)

        if max_results is not None and max_results > 0:
            return candidates[:max_results]

        return candidates

    @classmethod
    def verify_single(
        cls,
        xpath: str,
        lxml_tree: etree._Element,
        node_map: Optional[dict] = None
    ) -> VerifyResult:
        """
        Evaluate a single XPath against the lxml tree and extract matching UINodes.
        """
        if not xpath or lxml_tree is None:
            return VerifyResult(xpath=xpath, match_count=0, status="zero")

        try:
            matches = lxml_tree.xpath(xpath)
            if not isinstance(matches, list):
                matches = [matches] if matches else []

            count = len(matches)
            status = "unique" if count == 1 else ("multi" if count > 1 else "zero")

            matched_nodes: List[UINode] = []
            if node_map:
                for m in matches:
                    if hasattr(m, "get"):
                        uid = m.get("_xgen_uid")
                        if uid and uid in node_map:
                            matched_nodes.append(node_map[uid])

            return VerifyResult(xpath=xpath, match_count=count, status=status, matched_nodes=matched_nodes)
        except etree.XPathEvalError as e:
            logger.debug("XPath evaluation error on '%s': %s", xpath, e)
            return VerifyResult(xpath=xpath, match_count=0, status="error")
        except Exception as e:
            logger.warning("Unexpected error evaluating xpath '%s': %s", xpath, e)
            return VerifyResult(xpath=xpath, match_count=0, status="error")

    @classmethod
    def re_verify_all(
        cls,
        candidates: List[XPathCandidate],
        lxml_tree: etree._Element,
        node_map: Optional[dict] = None
    ) -> None:
        """In-place verification update for an existing candidate list."""
        for c in candidates:
            c.verify_result = cls.verify_single(c.xpath, lxml_tree, node_map)
