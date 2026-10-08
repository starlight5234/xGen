"""
Locator Engine.
Integrates xGen's XPathGenerator with the evidence tree to produce, score,
and verify ranked LocatorCandidate lists for recorded steps.
Zero Qt dependencies.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from lxml import etree

from xgen.core.driver_dialect import DriverDialect, active_dialect
from xgen.core.tree_parser import TreeParser, UINode
from xgen.core.xpath_generator import XPathGenerator
from xgen.recorder.locators.evidence_builder import EvidenceBuilder
from xgen.recorder.models import (
    CapturedContext, LocatorCandidate, LocatorState, SimilarFacts
)

logger = logging.getLogger("xgen.recorder.locators.engine")


class LocatorEngine:
    """
    Synthesizes and classifies ranked XPath locators from native interaction context.
    """

    def __init__(self, dialect: Optional[DriverDialect] = None):
        self.dialect = dialect or active_dialect()
        self.evidence_builder = EvidenceBuilder(dialect=self.dialect)
        self.generator = XPathGenerator()

    def generate_locators(self, ctx: CapturedContext,
                          similar_facts: Optional[SimilarFacts] = None) -> List[LocatorCandidate]:
        """
        Builds evidence tree, synthesizes tiered XPath locators using XPathGenerator,
        and verifies their uniqueness against the evidence tree.
        """
        # 1. Build evidence UINode tree
        root_node, target_node = self.evidence_builder.build_tree(ctx, similar_facts)

        # 2. Convert evidence tree to lxml for local XPath evaluation
        node_map: Dict[str, UINode] = {}
        try:
            lxml_root = TreeParser.to_xml_element(root_node, node_map)
        except Exception as e:
            logger.debug("Failed to build lxml element tree for evidence: %s", e)
            lxml_root = None

        # 3. Generate candidate XPaths using xGen's existing engine
        generated_candidates = self.generator.generate(target_node)
        if not generated_candidates:
            # Fallback basic tag or coordinates
            tag = target_node.tag
            return [
                LocatorCandidate(
                    xpath=f"//{tag}",
                    tier="fallback",
                    stability_score=20,
                    state=LocatorState.UNVERIFIED,
                    notes=["fallback_generic_tag"]
                )
            ]

        results: List[LocatorCandidate] = []

        # 4. Classify each candidate
        for cand in generated_candidates:
            state = self._classify_candidate_state(cand.xpath, cand.is_positional, lxml_root, target_node)
            loc = LocatorCandidate(
                xpath=cand.xpath,
                tier=cand.tier.value if hasattr(cand.tier, "value") else str(cand.tier),
                stability_score=cand.stability_score,
                stability_label=cand.stability_label,
                state=state,
                localization_risk=cand.localization_risk,
                is_positional=cand.is_positional,
                is_data_dependent=cand.is_data_dependent
            )
            results.append(loc)

        # 5. Sort by stability_score descending, prioritizing UNIQUE_IN_EVIDENCE
        results.sort(
            key=lambda c: (
                1 if c.state == LocatorState.UNIQUE_IN_EVIDENCE else 0,
                c.stability_score
            ),
            reverse=True
        )

        return results

    def _classify_candidate_state(self, xpath: str, is_positional: bool,
                                  lxml_root: Optional[etree._Element],
                                  target_node: UINode) -> LocatorState:
        # Positional index locators cannot be guaranteed unique in full app without complete tree
        if is_positional or bool(re.search(r'\[\s*\d+\s*\]', xpath)):
            return LocatorState.UNVERIFIED

        if lxml_root is None:
            return LocatorState.UNVERIFIED

        try:
            matches = lxml_root.xpath(xpath)
            if len(matches) == 1:
                return LocatorState.UNIQUE_IN_EVIDENCE
            if len(matches) > 1:
                return LocatorState.AMBIGUOUS
            return LocatorState.UNVERIFIED
        except Exception:
            return LocatorState.FAILED
