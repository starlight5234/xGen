"""
Evidence Tree Builder.
Constructs in-memory UINode trees from CapturedContext (target + ancestors + duplicates)
so xGen's existing XPathGenerator and verifier can operate directly without Appium.
Zero Qt dependencies.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from xgen.core.driver_dialect import DriverDialect, active_dialect
from xgen.core.tree_parser import UINode
from xgen.recorder.models import (
    CapturedContext, ElementFacts, ResolutionMethod, SimilarFacts
)
from xgen.utils.rect import Rect


class EvidenceBuilder:
    """
    Transforms native CapturedContext and duplicate facts into an in-memory UINode tree.
    """

    def __init__(self, dialect: Optional[DriverDialect] = None):
        self.dialect = dialect or active_dialect()

    def build_tree(self, ctx: CapturedContext,
                   similar_facts: Optional[SimilarFacts] = None) -> Tuple[UINode, UINode]:
        """
        Builds UINode hierarchy from ancestor chain down to target element.
        Returns:
            (root_node, target_node)
        """
        chain = ctx.chain
        confidence = self._confidence_for_resolution(ctx.resolution)

        # 1. Build target UINode
        target_node = self._element_to_uinode(chain.target, confidence)

        # 2. Build ancestor chain
        # ancestors are ordered: [immediate_parent, grandparent, ..., root_window]
        curr_node = target_node
        root_node = target_node

        if chain.ancestors:
            for ancestor_fact in chain.ancestors:
                ancestor_node = self._element_to_uinode(ancestor_fact, confidence)
                curr_node.parent = ancestor_node
                ancestor_node.children.append(curr_node)
                curr_node = ancestor_node
            root_node = curr_node
            # If the topmost ancestor is not a Window and window facts exist, anchor under Window
            if root_node.tag != "Window" and chain.window:
                win_title = chain.window.title or (chain.window.class_name if chain.window.class_name else "Window")
                win_fact = ElementFacts(
                    control_type="Window",
                    name=win_title,
                    class_name=chain.window.class_name,
                    bounds=chain.window.bounds,
                    native_handle=chain.window.handle
                )
                win_node = self._element_to_uinode(win_fact, confidence)
                root_node.parent = win_node
                win_node.children.append(root_node)
                root_node = win_node
        else:
            # If no ancestors recorded, synthesize a top-level window container from window facts
            if chain.window:
                win_title = chain.window.title or (chain.window.class_name if chain.window.class_name else "Window")
                win_fact = ElementFacts(
                    control_type="Window",
                    name=win_title,
                    class_name=chain.window.class_name,
                    bounds=chain.window.bounds,
                    native_handle=chain.window.handle
                )
                win_node = self._element_to_uinode(win_fact, confidence)
                target_node.parent = win_node
                win_node.children.append(target_node)
                root_node = win_node

        # 3. If duplicate/similar elements exist, add dummy duplicate siblings under root
        # so XPath generator and verifier can verify uniqueness
        if similar_facts and similar_facts.count > 1:
            # If root_node is target_node (no ancestors and no window container), synthesize a container
            # so duplicates are siblings under the container, NOT children of target_node
            if root_node is target_node:
                win_title = (chain.window.title if (chain.window and chain.window.title) else "") or (chain.window.class_name if chain.window else "") or "Window"
                win_fact = ElementFacts(
                    control_type="Window",
                    name=win_title,
                    class_name=chain.window.class_name if chain.window else "WindowClass",
                    bounds=chain.window.bounds if chain.window else None,
                    native_handle=chain.window.handle if chain.window else 0
                )
                win_node = self._element_to_uinode(win_fact, confidence)
                target_node.parent = win_node
                win_node.children.append(target_node)
                root_node = win_node

            for i in range(1, similar_facts.count):
                dup_fact = ElementFacts(
                    control_type=chain.target.control_type,
                    name=chain.target.name,
                    automation_id=f"{chain.target.automation_id}_dup_{i}",
                    class_name=chain.target.class_name
                )
                dup_node = self._element_to_uinode(dup_fact, confidence)
                dup_node.parent = root_node
                root_node.children.append(dup_node)

        # Assign depths
        self._assign_depths(root_node, 0)

        return root_node, target_node

    def _element_to_uinode(self, fact: ElementFacts, confidence: float) -> UINode:
        tag = fact.control_type or "Pane"
        if tag.endswith("Control"):
            tag = tag[:-7]

        # Sanitize tag into valid XML identifier without spaces
        tag = "".join(word.capitalize() for word in tag.split()) if tag else "Pane"
        tag = "".join(c for c in tag if c.isalnum() or c == "_")
        if not tag or tag[0].isdigit():
            tag = "Pane"

        attrib: Dict[str, str] = {
            "Name": fact.name,
            "AutomationId": fact.automation_id,
            "ClassName": fact.class_name,
            "ControlType": f"{tag}Control",
            "IsEnabled": str(fact.is_enabled).lower(),
            "IsOffscreen": str(fact.is_offscreen).lower(),
        }
        if fact.help_text:
            attrib["HelpText"] = fact.help_text

        b_rect = None
        if fact.bounds:
            b_rect = Rect(
                left=fact.bounds.left,
                top=fact.bounds.top,
                right=fact.bounds.right,
                bottom=fact.bounds.bottom
            )

        return UINode(
            tag=tag,
            attributes=attrib,
            parent=None,
            dialect=self.dialect,
            bridge_confidence=confidence,
            bounding_rect=b_rect,
            runtime_id=fact.runtime_id
        )

    @staticmethod
    def _confidence_for_resolution(res: ResolutionMethod) -> float:
        if res == ResolutionMethod.NATIVE_EXACT:
            return 1.0
        if res == ResolutionMethod.SCENE_CACHE:
            return 0.75
        return 0.3

    def _assign_depths(self, node: UINode, depth: int) -> None:
        node.depth = depth
        for child in node.children:
            self._assign_depths(child, depth + 1)
